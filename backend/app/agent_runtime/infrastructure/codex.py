import asyncio
import hashlib
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.agent_runtime.application.developer_progress_governor import DeveloperProgressGovernor
from app.agent_runtime.application.harness import HarnessSettings, TurnReceipt
from app.agent_runtime.domain.context_generation import CODEX_CAPABILITIES
from app.agent_runtime.infrastructure.checkpoints import workspace_facts
from app.agent_runtime.infrastructure.normalization import codex_usage
from app.agent_runtime.infrastructure.tool_logs import ToolLogs


class CodexHarness:
    """Pinned SDK adapter. Instantiate only inside the isolated developer runner.

    Docker persists /home/runner/.codex per task. The SDK supplies its own tool
    loop; this adapter does not implement file tools or replay old transcripts.
    """

    def __init__(
        self, settings: HarnessSettings, *, previous_usage: dict[str, Any] | None = None
    ) -> None:
        from openai_codex import AsyncCodex, CodexConfig

        self.settings = settings
        self.client = AsyncCodex(
            CodexConfig(
                cwd=str(settings.workspace),
                # Keep native sessions, not credentials, in the mounted task home.
                config_overrides=('cli_auth_credentials_store="ephemeral"',),
            )
        )
        self.thread: Any = None
        self.turn: Any = None
        self.previous_usage = previous_usage
        self.governor = DeveloperProgressGovernor(settings.token_policy)
        self.governor.restore(settings.progress_baseline)
        self.progress_offset = self.governor.total
        self.logs = ToolLogs(Path.home() / ".aew" / "tool-logs")
        self.compacting = False

    def _emit_progress(self) -> None:
        if self.settings.progress_callback:
            self.settings.progress_callback(self.governor.snapshot())

    async def _diff_progress(self) -> None:
        try:
            facts = await workspace_facts(self.settings.workspace, self.settings.workspace)
        except (OSError, ValueError, RuntimeError):
            return  # Missing observations never manufacture progress.
        if facts["changed_files"]:
            self.governor.progress(facts["diff_fingerprint"])

    @property
    def capabilities(self) -> dict[str, bool]:
        return asdict(CODEX_CAPABILITIES)

    def _options(self) -> dict[str, Any]:
        from openai_codex import ApprovalMode, Sandbox

        return {
            "cwd": str(self.settings.workspace),
            "model": self.settings.model,
            "sandbox": Sandbox.read_only if self.settings.read_only else Sandbox.workspace_write,
            "approval_mode": ApprovalMode.deny_all,
            "developer_instructions": self.settings.instructions,
            "config": {
                "features.multi_agent": False,
                "sandbox_workspace_write.network_access": False,
                "shell_environment_policy.inherit": "none",
                "tool_output_token_limit": self.settings.token_policy.max_model_visible_tool_result_tokens,
            },
        }

    async def _authenticate(self) -> None:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise ValueError("Native Codex requires an injected OpenAI API key")
        # App-server does not use OPENAI_API_KEY implicitly. This is a local
        # login operation; it must finish before creating/resuming a paid turn.
        await self.client.login_api_key(key)

    async def start(self) -> str:
        await self._authenticate()
        self.thread = await self.client.thread_start(**self._options(), ephemeral=False)
        self.previous_usage = dict.fromkeys(
            (
                "input_tokens",
                "output_tokens",
                "cached_input_tokens",
                "cache_write_input_tokens",
                "reasoning_output_tokens",
            ),
            0,
        )
        return str(self.thread.id)

    async def resume(self, native_session_id: str) -> None:
        if not native_session_id:
            raise ValueError("An explicit native thread ID is required")
        await self._authenticate()
        self.thread = await self.client.thread_resume(native_session_id, **self._options())

    async def run_turn(self, prompt: str) -> TurnReceipt:
        from openai_codex.generated.v2_all import ReasoningEffort

        if self.thread is None:
            raise RuntimeError("Start or resume a thread before running")
        if self.governor.diff_fingerprint is None:
            try:
                facts = await workspace_facts(self.settings.workspace, self.settings.workspace)
                self.governor.diff_fingerprint = facts["diff_fingerprint"]
            except (RuntimeError, OSError, ValueError):
                pass
        self.turn = await self.thread.turn(prompt, effort=ReasoningEffort(self.settings.effort))
        return await self._collect()

    async def _collect(self) -> TurnReceipt:
        from openai_codex.generated.v2_all import (
            AgentMessageThreadItem,
            CommandExecutionOutputDeltaNotification,
            CommandExecutionThreadItem,
            FileChangeThreadItem,
            ItemCompletedNotification,
            ThreadTokenUsageUpdatedNotification,
            TurnCompletedNotification,
            TurnDiffUpdatedNotification,
        )

        total: dict[str, Any] = {}
        summary = ""
        completed: Any = None
        interrupted_for_budget = False
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                async for event in self.turn.stream():
                    payload = event.payload
                    if isinstance(payload, CommandExecutionOutputDeltaNotification):
                        self.logs.append(f"{payload.turn_id}:{payload.item_id}", payload.delta)
                    elif isinstance(payload, ThreadTokenUsageUpdatedNotification):
                        # The pinned SDK specifies cache writes as zero when absent.
                        # Preserve that schema default; explicit null still means unknown.
                        total = payload.token_usage.total.model_dump()
                        usage = codex_usage(total, self.previous_usage)
                        warnings, stop = self.governor.observe(
                            self.progress_offset + (usage.input_tokens or 0),
                            payload.token_usage.last.input_tokens,
                            usage.cache_read_input_tokens,
                        )
                        self._emit_progress()
                        if stop and not interrupted_for_budget:
                            await self.turn.interrupt()
                        elif warnings and not self.compacting:
                            await self.turn.steer(
                                "Developer policy: "
                                + ", ".join(warnings)
                                + ". Use current evidence for a concrete edit or a bounded blocked result. "
                                "Do not repeat unchanged failed commands or broad reads."
                                + (
                                    " At the next safe boundary, finish with MILESTONE_COMPLETE on its own line, followed by completed work, decisions, remaining work and next action."
                                    if "CONTEXT_WARNING" in warnings
                                    and self.settings.token_policy.automatic_rollover
                                    else ""
                                )
                            )
                        cost = (
                            self.settings.pricing.calculate(usage)
                            if self.settings.pricing
                            else None
                        )
                        if not interrupted_for_budget and (
                            cost is None or cost >= self.settings.max_cost_usd
                        ):
                            interrupted_for_budget = True
                            await self.turn.interrupt()
                    elif isinstance(payload, ItemCompletedNotification):
                        item = payload.item.root
                        if isinstance(item, AgentMessageThreadItem):
                            summary = item.text[:8000]
                        elif getattr(item, "type", "") == "contextCompaction":
                            self.governor.compaction_count += 1
                            self.governor.phase = "COMPACTION"
                        elif (
                            isinstance(item, FileChangeThreadItem)
                            and item.status.value == "completed"
                        ):
                            await self._diff_progress()
                        elif isinstance(item, CommandExecutionThreadItem):
                            self.logs.finish(
                                f"{self.turn.id}:{item.id}",
                                {
                                    "source": "native-output-deltas",
                                    "exit_code": item.exit_code,
                                    "duration_ms": item.duration_ms,
                                    "command_sha256": hashlib.sha256(
                                        item.command.encode()
                                    ).hexdigest(),
                                },
                            )
                            fingerprint = hashlib.sha256(
                                (
                                    item.command
                                    + "\0"
                                    + str(item.exit_code)
                                    + "\0"
                                    + (item.aggregated_output or "")
                                ).encode()
                            ).hexdigest()
                            self.governor.command(
                                fingerprint,
                                failed=item.exit_code not in {None, 0},
                                expensive=(item.duration_ms or 0) >= 1000,
                            )
                            output_size = len((item.aggregated_output or "").encode())
                            if any(
                                word in item.command
                                for word in ("pytest", "test", "check", "build", "mypy", "ruff")
                            ):
                                self.governor.check(
                                    hashlib.sha256(item.command.encode()).hexdigest(),
                                    "passed" if item.exit_code == 0 else fingerprint,
                                )
                            self.governor.shell_output_bytes += output_size
                            for action in item.command_actions:
                                if action.root.type == "read":
                                    self.governor.read(fingerprint, output_size)
                            await self._diff_progress()
                    elif isinstance(payload, TurnDiffUpdatedNotification) and payload.diff:
                        await self._diff_progress()
                    elif isinstance(payload, TurnCompletedNotification):
                        completed = payload.turn
        except (TimeoutError, asyncio.CancelledError):
            await self.interrupt()
            raise
        if completed is None:
            raise RuntimeError("Native turn ended without completion evidence")
        usage = codex_usage(total, self.previous_usage)
        self.previous_usage = total or None
        failure_code = _failure_code(completed.error) if completed.error else None
        return TurnReceipt(
            native_session_id=str(self.thread.id),
            native_turn_id=str(completed.id),
            summary=summary or (failure_code or ""),
            status="interrupted"
            if interrupted_for_budget or self.governor.stop_reason
            else completed.status.value,
            usage=usage,
            raw_usage=total,
            cumulative_usage=total or None,
            provider_duration_ms=completed.duration_ms,
            failure_code=self.governor.stop_reason or failure_code,
            token_efficiency=self.governor.snapshot(),
        )

    async def compact(self) -> TurnReceipt:
        from openai_codex.api import AsyncTurnHandle
        from openai_codex.generated.v2_all import TurnStartedNotification

        if self.thread is None:
            raise RuntimeError("Compaction requires an existing thread")
        self.compacting = True
        async with asyncio.timeout(self.settings.timeout_seconds):
            await self.thread.compact()
            # The pinned high-level SDK returns only the start acknowledgement.
            # Its public low-level notification API supplies the compaction turn
            # handle; this narrow facade seam is covered by an SDK contract test.
            while True:
                event = await self.client._client.next_notification()
                payload = event.payload
                if (
                    isinstance(payload, TurnStartedNotification)
                    and payload.thread_id == self.thread.id
                ):
                    self.turn = AsyncTurnHandle(self.client, self.thread.id, payload.turn.id)
                    return await self._collect()

    async def interrupt(self) -> None:
        if self.turn is not None:
            await self.turn.interrupt()

    async def inspect(self) -> dict[str, Any]:
        if self.thread is None:
            return {"state": "not_started"}
        data = await self.thread.read(include_turns=False)
        return {
            "native_session_id": str(self.thread.id),
            "status": data.thread.status.model_dump(mode="json"),
        }

    async def close(self) -> None:
        await self.client.close()


def _failure_code(error: Any) -> str:
    """Persist only allowlisted metadata, never a provider error body or secret."""
    info = error.codex_error_info
    value = info.model_dump(mode="json") if info is not None else None
    if isinstance(value, dict):
        for detail in value.values():
            if isinstance(detail, dict):
                status = detail.get("httpStatusCode", detail.get("http_status_code"))
                if status in {401, 403}:
                    return "PROVIDER_AUTHENTICATION_FAILED"
                if status == 429:
                    return "PROVIDER_RATE_LIMIT"
    return {
        "unauthorized": "PROVIDER_AUTHENTICATION_FAILED",
        "usageLimitExceeded": "PROVIDER_RATE_LIMIT",
        "serverOverloaded": "PROVIDER_OUTAGE",
        "contextWindowExceeded": "NATIVE_CONTEXT_EXHAUSTED",
        "sessionBudgetExceeded": "NATIVE_BUDGET_EXHAUSTED",
    }.get(value if isinstance(value, str) else "", "NATIVE_TURN_FAILED")
