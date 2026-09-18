"""Bounded decision orchestration, independent of storage and provider SDKs."""

import asyncio
from typing import Any
from uuid import UUID

from app.coordinator.application.ports import (
    ConversationGateway,
    ConversationUnavailable,
    CoordinationRuns,
    DecisionModel,
    SituationChanged,
)


class ProcessCoordinator:
    def __init__(
        self,
        runs: CoordinationRuns,
        model: DecisionModel,
        conversations: ConversationGateway,
        *,
        watch_seconds: float = 1,
        timeout_seconds: float = 150,
    ) -> None:
        self.runs, self.model, self.conversations = runs, model, conversations
        self.watch_seconds, self.timeout_seconds = watch_seconds, timeout_seconds

    async def claim(self) -> tuple[UUID, UUID, str, dict[str, Any]] | None:
        return await self.runs.claim()

    async def recover(self) -> None:
        await self.runs.recover()

    async def _watch(self, run_id: UUID) -> None:
        interval = self.watch_seconds
        while True:
            await asyncio.sleep(interval)
            await self.runs.ensure_authorized(run_id)
            interval = min(interval * 2, max(self.watch_seconds, 5))

    async def _decide(
        self, run_id: UUID, task_id: UUID, provider: str, packet: dict[str, Any]
    ) -> None:
        decision = await self.model.decide(run_id, packet, 0)
        if decision.read_tools:
            evidence: dict[str, Any] = {}
            for tool in dict.fromkeys(decision.read_tools):
                try:
                    evidence[tool] = await self.conversations.read(task_id, provider, tool)
                except ConversationUnavailable as exc:
                    evidence[tool] = {"unavailable": exc.error_type}
                except (ValueError, LookupError, TimeoutError, OSError) as exc:
                    evidence[tool] = {"unavailable": type(exc).__name__}
            packet["requested_evidence"] = evidence
            decision = await self.model.decide(run_id, packet, 1)
            if decision.read_tools:
                raise ValueError("Coordinator exhausted its context expansion")
        await self.runs.ensure_authorized(run_id)
        await self.runs.complete(run_id, task_id, decision, packet)

    async def process_one(self) -> bool:
        claimed = await self.claim()
        if claimed is None:
            return False
        run_id, task_id, provider, packet = claimed
        operation = asyncio.create_task(self._decide(run_id, task_id, provider, packet))
        watcher = asyncio.create_task(self._watch(run_id))
        try:
            async with asyncio.timeout(self.timeout_seconds):
                finished, _ = await asyncio.wait(
                    {operation, watcher}, return_when=asyncio.FIRST_COMPLETED
                )
                if operation in finished:
                    operation.result()
                else:
                    watcher.result()
        except BaseException as exc:
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            await self.runs.fail(
                run_id,
                str(exc)[:500] if type(exc) is ValueError else type(exc).__name__,
                superseded=isinstance(exc, SituationChanged),
            )
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            operation.cancel()
            watcher.cancel()
            await asyncio.gather(operation, watcher, return_exceptions=True)
        return True
