import asyncio
from typing import Any

from app.agent_runtime.application.harness import HarnessSettings, TurnReceipt
from app.agent_runtime.infrastructure.normalization import codex_usage


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
        self.client = AsyncCodex(CodexConfig(cwd=str(settings.workspace)))
        self.thread: Any = None
        self.turn: Any = None
        self.previous_usage = previous_usage

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
            },
        }

    async def start(self) -> str:
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
        self.thread = await self.client.thread_resume(native_session_id, **self._options())

    async def run_turn(self, prompt: str) -> TurnReceipt:
        from openai_codex.generated.v2_all import ReasoningEffort

        if self.thread is None:
            raise RuntimeError("Start or resume a thread before running")
        self.turn = await self.thread.turn(prompt, effort=ReasoningEffort(self.settings.effort))
        return await self._collect()

    async def _collect(self) -> TurnReceipt:
        from openai_codex.generated.v2_all import (
            AgentMessageThreadItem,
            ItemCompletedNotification,
            ThreadTokenUsageUpdatedNotification,
            TurnCompletedNotification,
        )

        total: dict[str, Any] = {}
        summary = ""
        completed: Any = None
        interrupted_for_budget = False
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                async for event in self.turn.stream():
                    payload = event.payload
                    if isinstance(payload, ThreadTokenUsageUpdatedNotification):
                        # The pinned SDK specifies cache writes as zero when absent.
                        # Preserve that schema default; explicit null still means unknown.
                        total = payload.token_usage.total.model_dump()
                        usage = codex_usage(total, self.previous_usage)
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
                    elif isinstance(payload, TurnCompletedNotification):
                        completed = payload.turn
        except (TimeoutError, asyncio.CancelledError):
            await self.interrupt()
            raise
        if completed is None:
            raise RuntimeError("Native turn ended without completion evidence")
        usage = codex_usage(total, self.previous_usage)
        self.previous_usage = total or None
        return TurnReceipt(
            native_session_id=str(self.thread.id),
            native_turn_id=str(completed.id),
            summary=summary,
            status="interrupted" if interrupted_for_budget else completed.status.value,
            usage=usage,
            raw_usage=total,
            cumulative_usage=total or None,
            provider_duration_ms=completed.duration_ms,
        )

    async def compact(self) -> TurnReceipt:
        from openai_codex.api import AsyncTurnHandle
        from openai_codex.generated.v2_all import TurnStartedNotification

        if self.thread is None:
            raise RuntimeError("Compaction requires an existing thread")
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
