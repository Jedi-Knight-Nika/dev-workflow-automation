from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.agent_runtime.application.harness import DeveloperHarness, TurnReceipt
from app.agent_runtime.domain.usage import budget_blocker


@dataclass(frozen=True)
class SessionContext:
    task_id: UUID
    native_session_id: str | None
    requirement_version: int
    initial_request: str
    checkpoint: str = ""


class DevelopmentStore(Protocol):
    """Each method verifies the task lease and pause state transactionally."""

    async def assert_runnable(self, task_id: UUID) -> None: ...
    async def consumed_cost(self, task_id: UUID) -> Decimal | None: ...
    async def session_started(self, task_id: UUID, native_id: str) -> None: ...
    async def begin_run(self, task_id: UUID, requirement_version: int) -> UUID: ...
    async def finish_run(self, run_id: UUID, receipt: TurnReceipt) -> None: ...
    async def fail_run(
        self, run_id: UUID, code: str, *, inference_started: bool = True
    ) -> None: ...


class DevelopmentBlocked(ValueError):
    pass


class DevelopTask:
    def __init__(
        self, harness: DeveloperHarness, store: DevelopmentStore, hard_budget: Decimal
    ) -> None:
        self.harness, self.store, self.hard_budget = harness, store, hard_budget

    async def execute(
        self, context: SessionContext, *, feedback: str | None = None, compaction: bool = False
    ) -> TurnReceipt:
        await self.store.assert_runnable(context.task_id)
        blocker = budget_blocker(
            hard_limit=self.hard_budget, consumed=await self.store.consumed_cost(context.task_id)
        )
        if blocker:
            raise DevelopmentBlocked(blocker)
        if feedback is not None and not context.native_session_id:
            raise DevelopmentBlocked(
                "Repair requires its persisted native session; do not silently restart"
            )
        # A resumed turn receives only the new information. Full transcripts,
        # source files and duplicate plans are owned by the native session.
        prompt = feedback if feedback is not None else context.initial_request
        if not prompt.strip() or len(prompt) > 24000:
            raise DevelopmentBlocked("Provide a bounded, nonempty task or feedback delta")
        run_id = await self.store.begin_run(context.task_id, context.requirement_version)
        inference_started = False
        try:
            if context.native_session_id:
                await self.harness.resume(context.native_session_id)
            else:
                native_id = await self.harness.start()
                # Persist before executing: a crash must not lose the session ID.
                await self.store.session_started(context.task_id, native_id)
            await self.store.assert_runnable(context.task_id)
            inference_started = True
            receipt = (
                await self.harness.compact() if compaction else await self.harness.run_turn(prompt)
            )
            await self.store.finish_run(run_id, receipt)
            return receipt
        except BaseException as exc:
            # Stop the paid process before attempting database recovery. A database
            # outage must not leave inference running while fail_run waits for a pool.
            try:
                await self.harness.interrupt()
            finally:
                await self.store.fail_run(
                    run_id, type(exc).__name__, inference_started=inference_started
                )
            raise
        finally:
            await self.harness.close()


def checkpoint_payload(receipt: TurnReceipt, requirement_version: int) -> dict[str, Any]:
    return {
        "summary": receipt.summary[-8000:],
        "native_session_id": receipt.native_session_id,
        "native_turn_id": receipt.native_turn_id,
        "requirement_version": requirement_version,
        "cumulative_usage": receipt.cumulative_usage,
    }
