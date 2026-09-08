import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.agent_runtime.application.harness import HarnessSettings, TurnReceipt
from app.agent_runtime.infrastructure.normalization import claude_usage


class ClaudeHarness:
    """Claude SDK adapter; requires the same task-scoped OS isolation as Codex."""

    def __init__(self, settings: HarnessSettings) -> None:
        self.settings = settings
        self.native_session_id = ""
        self.client: Any = None

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
                if not path.resolve().is_relative_to(self.settings.workspace.resolve()):
                    return PermissionResultDeny(message="Path is outside the task workspace")
        return PermissionResultAllow(updated_input=inputs)

    async def _connect(self, *, resume: bool) -> None:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

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
        from claude_agent_sdk import ResultMessage

        if self.client is None:
            raise RuntimeError("Start or resume a session before running")
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                await self.client.query(prompt)
                async for message in self.client.receive_response():
                    if isinstance(message, ResultMessage):
                        self.native_session_id = message.session_id
                        raw = message.usage or {}
                        return TurnReceipt(
                            native_session_id=message.session_id,
                            native_turn_id=message.uuid or str(uuid4()),
                            summary=(message.result or "")[:8000],
                            status="failed" if message.is_error else "completed",
                            usage=claude_usage(raw, message.total_cost_usd),
                            raw_usage=raw,
                            provider_duration_ms=message.duration_api_ms,
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
