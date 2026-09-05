import asyncio
import hashlib
import json
import os
import re
import signal
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psutil
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApprovalRequest, ToolExecutionEvent
from app.domain.security import ActionRequest, Decision, TeamExecutionPolicy
from app.domain.security.paths import resolve_workspace_path
from app.domain.security.policy import evaluate

SECRET = re.compile(r"(?i)(token|secret|password|api[_-]?key)(\s*[=:]\s*)([^\s]+)")
PROTECTED_ENVIRONMENT_KEYS = frozenset({"HOME", "PATH", "USERPROFILE"})


class ToolDenied(PermissionError):
    pass


class ToolNeedsApproval(PermissionError):
    def __init__(self, approval_id: uuid.UUID) -> None:
        self.approval_id = approval_id
        super().__init__(f"Human approval required: {approval_id}")


@dataclass(frozen=True, slots=True)
class GatewayContext:
    team_id: uuid.UUID
    task_id: uuid.UUID
    job_id: uuid.UUID
    agent_id: uuid.UUID | None
    role_id: uuid.UUID | None
    workspace: Path
    task_branch: str | None
    permissions: frozenset[str]


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool
    timed_out: bool


class ToolGateway:
    def __init__(
        self, session: AsyncSession, context: GatewayContext, policy: TeamExecutionPolicy
    ) -> None:
        self._session, self._context, self._policy = session, context, policy

    async def write_file(self, relative: str, content: str) -> None:
        path = resolve_workspace_path(self._context.workspace, relative)
        permission = "CREATE_FILES" if not path.exists() else "WRITE_REPOSITORY"
        await self._authorize("filesystem", "write", permission, {"path": relative})
        path.parent.mkdir(parents=True, exist_ok=True)
        path = resolve_workspace_path(self._context.workspace, relative)
        if path.is_symlink():
            raise ToolDenied("Refusing to replace a symlink")
        path.write_text(content, encoding="utf-8")

    async def delete_file(self, relative: str) -> None:
        path = resolve_workspace_path(self._context.workspace, relative, must_exist=True)
        await self._authorize("filesystem", "delete", "DELETE_FILES", {"path": relative})
        if path.is_symlink() or not path.is_file():
            raise ToolDenied("Only regular workspace files may be deleted")
        path.unlink()

    async def run_command(
        self,
        command: list[str],
        *,
        capability: str = "RUN_COMMANDS",
        timeout_seconds: int = 60,
        environment: dict[str, str] | None = None,
    ) -> CommandResult:
        if not command:
            raise ToolDenied("Empty command")
        timeout = min(max(timeout_seconds, 1), self._policy.max_command_timeout_seconds)
        await self._authorize(
            "shell",
            "execute",
            capability,
            {"command": command, "timeout_seconds": timeout},
            tuple(command),
        )
        worker_home = self._context.workspace / ".worker-home"
        worker_home.mkdir(mode=0o700, exist_ok=True)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "CI": "true",
            "HOME": str(worker_home),
        }
        env.update(
            {
                key: value
                for key, value in (environment or {}).items()
                if key.upper() not in PROTECTED_ENVIRONMENT_KEYS
            }
        )
        started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self._context.workspace,
            env=env,
            start_new_session=os.name != "nt",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except TimeoutError:
            timed_out = True
            await self._terminate_tree(process.pid)
            stdout, stderr = await process.communicate()
        limit = self._policy.max_output_bytes
        truncated = len(stdout) > limit or len(stderr) > limit
        clean_out = self._sanitize(stdout[-limit:].decode(errors="replace"), environment or {})
        clean_err = self._sanitize(stderr[-limit:].decode(errors="replace"), environment or {})
        result = CommandResult(
            tuple(command),
            process.returncode or (-1 if timed_out else 0),
            clean_out,
            clean_err,
            round((time.monotonic() - started) * 1000),
            truncated,
            timed_out,
        )
        await self._audit(
            "shell",
            "execute",
            Decision.ALLOW,
            "executed",
            {"command": command},
            result.exit_code,
            result.duration_ms,
        )
        return result

    async def authorize_push(self, target_branch: str) -> None:
        await self._authorize(
            "git",
            "push",
            "PUSH_TASK_BRANCH",
            {"target_branch": target_branch},
            target_branch=target_branch,
        )

    async def _authorize(
        self,
        tool: str,
        action: str,
        permission: str,
        arguments: dict[str, Any],
        command: tuple[str, ...] = (),
        target_branch: str | None = None,
    ) -> None:
        decision = evaluate(
            self._policy,
            ActionRequest(
                tool,
                action,
                permission,
                self._context.permissions,
                command,
                target_branch,
                self._context.task_branch,
            ),
        )
        await self._audit(tool, action, decision.decision, decision.policy_rule, arguments)
        if decision.decision == Decision.DENY:
            raise ToolDenied(decision.reason)
        if decision.decision == Decision.REQUIRE_HUMAN:
            payload = self._sanitized(arguments)
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            arguments_hash = hashlib.sha256(encoded).hexdigest()
            approved = await self._session.scalar(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.task_id == self._context.task_id,
                    ApprovalRequest.tool == tool,
                    ApprovalRequest.action == action,
                    ApprovalRequest.arguments_hash == arguments_hash,
                    ApprovalRequest.state == "APPROVED",
                    ApprovalRequest.expires_at > datetime.now(UTC),
                )
                .order_by(ApprovalRequest.resolved_at.desc())
            )
            if approved is not None and (
                approved.resolution_scope == "TASK" or approved.job_id == self._context.job_id
            ):
                if approved.resolution_scope == "ONCE":
                    approved.state = "CONSUMED"
                    await self._session.commit()
                await self._audit(tool, action, Decision.ALLOW, "approval.bound_action", arguments)
                return
            pending = await self._session.scalar(
                select(ApprovalRequest.id).where(
                    ApprovalRequest.job_id == self._context.job_id,
                    ApprovalRequest.tool == tool,
                    ApprovalRequest.action == action,
                    ApprovalRequest.arguments_hash == arguments_hash,
                    ApprovalRequest.state == "PENDING",
                    ApprovalRequest.expires_at > datetime.now(UTC),
                )
            )
            if pending is not None:
                raise ToolNeedsApproval(pending)
            approval = ApprovalRequest(
                team_id=self._context.team_id,
                task_id=self._context.task_id,
                job_id=self._context.job_id,
                agent_id=self._context.agent_id,
                tool=tool,
                action=action,
                arguments=payload,
                arguments_hash=arguments_hash,
                reason=decision.reason,
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            )
            self._session.add(approval)
            await self._session.commit()
            raise ToolNeedsApproval(approval.id)

    async def _audit(
        self,
        tool: str,
        action: str,
        decision: Decision,
        rule: str,
        arguments: dict[str, Any],
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        self._session.add(
            ToolExecutionEvent(
                team_id=self._context.team_id,
                task_id=self._context.task_id,
                job_id=self._context.job_id,
                agent_id=self._context.agent_id,
                role_id=self._context.role_id,
                tool=tool,
                action=action,
                decision=decision.value,
                policy_rule=rule,
                arguments_sanitized=self._sanitized(arguments),
                exit_code=exit_code,
                duration_ms=duration_ms,
            )
        )
        await self._session.commit()

    @staticmethod
    def _sanitized(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            key: "[REDACTED]"
            if any(word in key.casefold() for word in ("token", "secret", "password", "key"))
            else value
            for key, value in arguments.items()
        }

    @staticmethod
    def _sanitize(value: str, environment: dict[str, str]) -> str:
        value = SECRET.sub(r"\1\2[REDACTED]", value)
        for key, secret in environment.items():
            if secret and any(
                word in key.casefold() for word in ("token", "secret", "password", "key")
            ):
                value = value.replace(secret, "[REDACTED]")
        return value

    @staticmethod
    async def _terminate_tree(pid: int) -> None:
        if os.name != "nt":
            try:
                os.killpg(pid, signal.SIGKILL)
                return
            except ProcessLookupError:
                return
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for process in children:
                process.kill()
            parent.kill()
            await asyncio.to_thread(psutil.wait_procs, children + [parent], 3)
        except psutil.Error:
            return
