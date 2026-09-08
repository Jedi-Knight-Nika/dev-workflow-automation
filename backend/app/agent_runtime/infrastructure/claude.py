import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

from app.agent_runtime.application.developer_progress_governor import DeveloperProgressGovernor
from app.agent_runtime.application.harness import HarnessSettings, TurnReceipt
from app.agent_runtime.domain.context_generation import CLAUDE_CAPABILITIES
from app.agent_runtime.infrastructure.checkpoints import workspace_facts
from app.agent_runtime.infrastructure.normalization import claude_usage
from app.agent_runtime.infrastructure.tool_logs import ToolLogs


class ClaudeHarness:
    """Claude SDK adapter; requires the same task-scoped OS isolation as Codex."""

    def __init__(self, settings: HarnessSettings) -> None:
        self.settings = settings
        self.native_session_id = ""
        self.client: Any = None
        self.governor = DeveloperProgressGovernor(settings.token_policy)
        self.governor.restore(settings.progress_baseline)
        self.progress_offset = self.governor.total
        self.usage_by_message: dict[str, int] = {}
        self.pending_warning: list[str] = []
        self.logs = ToolLogs(Path.home() / ".aew" / "tool-logs")
        self.tool_started: dict[str, float] = {}

    async def _pre_tool(self, event: Any, identifier: Any, context: Any) -> Any:
        self.tool_started[str(event.get("tool_use_id") or identifier)] = monotonic()
        return {}

    async def _failed_tool(self, event: Any, identifier: Any, context: Any) -> Any:
        key = str(event.get("tool_use_id") or identifier)
        command = json.dumps(event.get("tool_input", {}), sort_keys=True)
        fingerprint = hashlib.sha256((command + str(event.get("error", ""))).encode()).hexdigest()
        self.governor.command(
            fingerprint,
            failed=True,
            expensive=monotonic() - self.tool_started.pop(key, monotonic()) >= 1,
        )
        self.logs.result(key, {"error": event.get("error")}, 4000)
        return {}

    async def _post_tool(self, event: Any, identifier: Any, context: Any) -> Any:
        response = event.get("tool_response")
        tool = event.get("tool_name")
        fingerprint = hashlib.sha256(
            json.dumps(event.get("tool_input", {}), sort_keys=True).encode()
        ).hexdigest()
        size = len(json.dumps(response).encode())
        if tool in {"Read", "Grep", "Glob"}:
            self.governor.read(fingerprint, size)
        if tool == "Bash":
            self.governor.shell_output_bytes += size
            duration = monotonic() - self.tool_started.pop(
                str(event.get("tool_use_id") or identifier), monotonic()
            )
            self.governor.command(
                fingerprint, failed=bool(event.get("error")), expensive=duration >= 1
            )
        if tool in {"Bash", "Edit", "Write"}:
            try:
                facts = await workspace_facts(self.settings.workspace, self.settings.workspace)
                if facts["changed_files"]:
                    self.governor.progress(facts["diff_fingerprint"])
            except (RuntimeError, OSError, ValueError):
                pass
        bounded = self.logs.result(
            str(event.get("tool_use_id") or identifier),
            response,
            self.settings.token_policy.max_model_visible_tool_result_tokens,
        )
        output: dict[str, Any] = {"hookEventName": "PostToolUse", "updatedToolOutput": bounded}
        if self.pending_warning:
            output["additionalContext"] = (
                "Developer policy: "
                + ", ".join(self.pending_warning)
                + ". Narrow reads; make a concrete edit or return blocked."
            )
            self.pending_warning.clear()
        if self.settings.progress_callback:
            self.settings.progress_callback(self.governor.snapshot())
        return {"hookSpecificOutput": output}

    @property
    def capabilities(self) -> dict[str, bool]:
        return asdict(CLAUDE_CAPABILITIES)

    async def _permission(self, tool: str, inputs: dict[str, Any], context: Any) -> Any:
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        # Paths are checked after symlink resolution. Shell commands still need
        # the runner's OS sandbox; string matching is not a shell security model.
        allowed = (
            {"Read", "Glob", "Grep"}
            if self.settings.read_only
            else {"Read", "Edit", "Write", "Glob", "Grep", "Bash"}
        )
        if tool not in allowed:
            return PermissionResultDeny(message="Tool is outside the Developer role")
        for field in ("file_path", "path"):
            if value := inputs.get(field):
                path = Path(str(value))
                path = path if path.is_absolute() else self.settings.workspace / path
                log_read = (
                    tool == "Read"
                    and path.resolve().is_relative_to(self.logs.root)
                    and not self.logs.root.is_symlink()
                )
                if not log_read and not path.resolve().is_relative_to(
                    self.settings.workspace.resolve()
                ):
                    return PermissionResultDeny(message="Path is outside the task workspace")
        if tool == "Read":
            inputs = {**inputs, "limit": min(int(inputs.get("limit", 200)), 400)}
        return PermissionResultAllow(updated_input=inputs)

    async def _connect(self, *, resume: bool) -> None:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

        options = ClaudeAgentOptions(
            model=self.settings.model,
            cwd=self.settings.workspace,
            tools=["Read", "Glob", "Grep"]
            if self.settings.read_only
            else ["Read", "Edit", "Write", "Glob", "Grep", "Bash"],
            disallowed_tools=["Agent", "Task", "WebSearch", "WebFetch"],
            allowed_tools=[],
            permission_mode="default",
            can_use_tool=self._permission,
            setting_sources=[],
            strict_mcp_config=True,
            hooks={
                "PostToolUse": [HookMatcher(hooks=[self._post_tool])],
                "PreToolUse": [HookMatcher(hooks=[self._pre_tool])],
                "PostToolUseFailure": [HookMatcher(hooks=[self._failed_tool])],
            },
            env={
                "BASH_MAX_OUTPUT_LENGTH": str(
                    self.settings.token_policy.max_model_visible_tool_result_tokens
                )
            },
            mcp_servers={},
            system_prompt={
                "type": "preset",
                "preset": "claude_code",
                "append": self.settings.instructions,
            },
            max_turns=self.settings.max_turns,
            max_budget_usd=float(self.settings.max_cost_usd),
            effort=self.settings.effort,  # type: ignore[arg-type]
            resume=self.native_session_id if resume else None,
            session_id=None if resume else self.native_session_id,
        )
        self.client = ClaudeSDKClient(options)
        await self.client.connect()

    async def start(self) -> str:
        self.native_session_id = str(uuid4())
        await self._connect(resume=False)
        return self.native_session_id

    async def resume(self, native_session_id: str) -> None:
        if not native_session_id:
            raise ValueError("An explicit native session ID is required")
        self.native_session_id = native_session_id
        await self._connect(resume=True)

    async def run_turn(self, prompt: str) -> TurnReceipt:
        from claude_agent_sdk import AssistantMessage, ResultMessage

        if self.client is None:
            raise RuntimeError("Start or resume a session before running")
        if self.governor.diff_fingerprint is None:
            try:
                facts = await workspace_facts(self.settings.workspace, self.settings.workspace)
                self.governor.diff_fingerprint = facts["diff_fingerprint"]
            except (RuntimeError, OSError, ValueError):
                pass
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                await self.client.query(prompt)
                async for message in self.client.receive_response():
                    if (
                        isinstance(message, AssistantMessage)
                        and message.usage
                        and message.message_id
                    ):
                        usage = claude_usage(message.usage, None)
                        if usage.input_tokens is not None:
                            self.usage_by_message[message.message_id] = usage.input_tokens
                            warnings, stop = self.governor.observe(
                                self.progress_offset + sum(self.usage_by_message.values()),
                                usage.input_tokens,
                            )
                            self.pending_warning.extend(warnings)
                            if stop:
                                await self.interrupt()
                    if isinstance(message, ResultMessage):
                        self.native_session_id = message.session_id
                        raw = message.usage or {}
                        return TurnReceipt(
                            native_session_id=message.session_id,
                            native_turn_id=message.uuid or str(uuid4()),
                            summary=(message.result or "")[:8000],
                            status="interrupted"
                            if self.governor.stop_reason
                            else "failed"
                            if message.is_error
                            else "completed",
                            usage=claude_usage(raw, message.total_cost_usd),
                            raw_usage=raw,
                            provider_duration_ms=message.duration_api_ms,
                            token_efficiency=self.governor.snapshot(),
                            failure_code=self.governor.stop_reason,
                        )
        except (TimeoutError, asyncio.CancelledError):
            await self.interrupt()
            raise
        raise RuntimeError("Claude ended without a result; usage is unknown")

    async def compact(self) -> TurnReceipt:
        return await self.run_turn("/compact")

    async def interrupt(self) -> None:
        if self.client is not None:
            await self.client.interrupt()

    async def inspect(self) -> dict[str, Any]:
        return {"native_session_id": self.native_session_id, "connected": self.client is not None}

    async def close(self) -> None:
        if self.client is not None:
            await self.client.disconnect()
            self.client = None
