"""Interactive edits and validation within an Executor's assigned workspaces."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any

from pydantic import model_validator

from app.domain.security.paths import resolve_workspace_path
from app.infrastructure.tools.gateway import ToolGateway, ToolNeedsApproval, ToolOperationError
from app.infrastructure.workers.executor import ExecutorProposal, run_checks
from app.infrastructure.workers.repository_tools import RepositoryTools, source_path_allowed


def _definition(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    fields = {"repository": {"type": "string"}, **properties}
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": fields,
            "required": list(fields),
            "additionalProperties": False,
        },
    }


EXECUTOR_TOOLS = (
    _definition(
        "read_workspace_file",
        "Read a current workspace file, including a file you created. Repository must be an exact workspace key.",
        {"path": {"type": "string"}},
    ),
    _definition(
        "edit_workspace_file",
        "Replace exactly one occurrence of old_text with new_text. Read the file first. For a NEW file only, use empty old_text and full content as new_text. The runtime performs the replacement; never invent diff hunk counts.",
        {
            "path": {"type": "string"},
            "old_text": {"type": "string", "maxLength": 100000},
            "new_text": {"type": "string", "maxLength": 100000},
        },
    ),
    _definition(
        "run_workspace_command",
        "Run a non-interactive command argument array inside a workspace directory. Requires RUN_COMMANDS permission. Output and failure are returned for correction. No credentials are supplied to arbitrary commands.",
        {
            "command": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 100,
            },
            "directory": {"type": "string"},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120},
        },
    ),
    _definition(
        "run_workspace_checks",
        "Run detected dependency setup and validation commands in a workspace directory, e.g. frontend or backend. Returns captured test/lint errors; fix them before finalizing.",
        {"directory": {"type": "string"}},
    ),
    _definition(
        "delete_workspace_file",
        "Delete one task-scoped file. Requires DELETE_FILES permission.",
        {"path": {"type": "string"}},
    ),
)


class InteractiveExecutorProposal(ExecutorProposal):
    @model_validator(mode="after")
    def edits_are_already_applied(self) -> "InteractiveExecutorProposal":
        if self.files or self.patches or self.delete_files:
            raise ValueError(
                "Apply changes with workspace tools first; final files, patches, delete_files must be empty to avoid applying changes twice"
            )
        return self


class ExecutorTools(RepositoryTools):
    def __init__(
        self,
        *args: Any,
        gateways: dict[str, ToolGateway],
        credential_environment: dict[str, str] | None = None,
        is_cancelled: Callable[[], Awaitable[bool]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.gateways = gateways
        self.credential_environment = credential_environment
        self.approval_id: str | None = None
        self.is_cancelled = is_cancelled
        self.validation_directories: dict[str, set[str]] = {}

    async def execute(self, name: str, arguments: str) -> str:
        self.last_trace = {}
        if self.is_cancelled is not None and await self.is_cancelled():
            raise RuntimeError("Worker cancelled before workspace operation")
        operation = asyncio.create_task(self._execute(name, arguments))
        try:
            while not operation.done():
                if self.is_cancelled is not None and await self.is_cancelled():
                    raise RuntimeError("Worker cancelled during workspace operation")
                await asyncio.wait({operation}, timeout=1)
            output = await operation
            if not self.last_trace:
                result = json.loads(output)
                self.last_trace = {
                    "tool": name,
                    "output_bytes": len(output.encode()),
                    "status": result.get("status"),
                    "exit_code": result.get("exit_code"),
                    "remaining_source_bytes": self.remaining,
                }
            return output
        finally:
            if not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)

    async def _execute(self, name: str, arguments: str) -> str:
        if name not in {item["name"] for item in EXECUTOR_TOOLS}:
            return await super().execute(name, arguments)
        self.calls += 1
        if self.calls > self.max_calls:
            raise RuntimeError("Repository tool-call budget exhausted")
        try:
            args = json.loads(arguments)
            if not isinstance(args, dict):
                raise TypeError("Tool arguments must be an object")
            key = args.get("repository")
            if not isinstance(key, str) or key not in self.gateways:
                raise ValueError("Choose an exact repository workspace key")
            gateway = self.gateways[key]
            workspace = dict(self.workspaces)[key]
            result: Any
            if name in {"read_workspace_file", "edit_workspace_file", "delete_workspace_file"}:
                relative = args.get("path")
                if not isinstance(relative, str) or not source_path_allowed(relative):
                    raise ValueError("Provide a non-secret workspace file path")
                path = resolve_workspace_path(workspace, relative)
                if not source_path_allowed(path.relative_to(workspace.resolve()).as_posix()):
                    raise PermissionError("Resolved path is not an allowed source file")
                if name == "delete_workspace_file":
                    await gateway.delete_file(relative)
                    self.begin_history()
                    result = {"status": "DELETED", "path": relative}
                elif name == "read_workspace_file":
                    content = await gateway.read_file(relative, max_bytes=max(0, self.remaining))
                    self.remaining -= len(content.encode())
                    result = {"path": relative, "content": content}
                else:
                    old, new = args.get("old_text"), args.get("new_text")
                    if (
                        not isinstance(old, str)
                        or not isinstance(new, str)
                        or max(len(old), len(new)) > 100_000
                    ):
                        raise ValueError("Provide bounded old_text and new_text strings")
                    if not old:
                        if path.exists():
                            raise ToolOperationError(
                                "File exists; use a unique nonempty old_text to edit it"
                            )
                        await gateway.write_file(relative, new)
                    else:
                        current = await gateway.read_file(relative)
                        if current.count(old) != 1:
                            raise ToolOperationError(
                                "old_text must match exactly once; read current contents and choose a unique span"
                            )
                        updated = current.replace(old, new, 1)
                        # Gateway writes enforce exactly the same workspace and role policy.
                        # Exact matching above avoids asking the model to generate diff syntax.
                        await gateway.write_file(relative, updated)
                    self.begin_history()  # Edits invalidate previous source-read references.
                    result = {"status": "APPLIED", "path": relative}
            elif name == "run_workspace_command":
                command = args.get("command")
                timeout, directory = args.get("timeout_seconds"), args.get("directory")
                if (
                    not isinstance(command, list)
                    or not 1 <= len(command) <= 100
                    or not all(isinstance(part, str) for part in command)
                ):
                    raise ValueError("Provide a nonempty command argument array")
                if (
                    type(timeout) is not int
                    or not 1 <= timeout <= 120
                    or not isinstance(directory, str)
                ):
                    raise ValueError("Provide directory and timeout_seconds between 1 and 120")
                outcome = await gateway.run_command(
                    command, timeout_seconds=timeout, directory=directory
                )
                checked_directory = resolve_workspace_path(workspace, directory, must_exist=True)
                self.validation_directories.setdefault(key, set()).add(
                    checked_directory.relative_to(workspace.resolve()).as_posix()
                )
                result = asdict(outcome)
                result["stdout"] = outcome.stdout[-6000:]
                result["stderr"] = outcome.stderr[-6000:]
                self.begin_history()  # Commands, formatters and tests can modify files.
            else:
                directory = args.get("directory")
                if not isinstance(directory, str):
                    raise ValueError("Provide a workspace directory")
                target = resolve_workspace_path(workspace, directory, must_exist=True)
                if not target.is_dir():
                    raise ValueError("Check directory must be a directory")
                directory = target.relative_to(workspace.resolve()).as_posix()
                self.validation_directories.setdefault(key, set()).add(directory)
                checks = await run_checks(
                    target,
                    gateway=gateway,
                    directory=directory,
                    credential_environment=self.credential_environment,
                    timeout_seconds=120,
                )
                result = {
                    "checks": [check.model_dump(mode="json") for check in checks],
                    "passed": bool(checks) and all(check.passed for check in checks),
                }
                self.begin_history()
            return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        except ToolNeedsApproval as exc:
            self.approval_id = str(exc.approval_id)
            return json.dumps({"status": "APPROVAL_REQUIRED", "approval_id": self.approval_id})
        except (ToolOperationError, PermissionError, OSError, ValueError, TypeError) as exc:
            return json.dumps(
                {
                    "status": "ERROR",
                    "message": str(exc)[:1000],
                    "correctable": not isinstance(exc, PermissionError),
                }
            )
