import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.engineering.application.jobs import (
    PhaseBlocked,
    PhaseExecutor,
    PhaseJobs,
    PhaseLease,
    RunEngineeringJob,
)
from app.engineering.domain.lifecycle import Action, WaitReason


def setup() -> tuple[PhaseLease, AsyncMock, AsyncMock]:
    lease = PhaseLease(uuid4(), uuid4(), uuid4(), "DEVELOPER_TURN", 3)
    jobs, executor = AsyncMock(spec=PhaseJobs), AsyncMock(spec=PhaseExecutor)
    jobs.heartbeat.return_value = True
    executor.execute.return_value = Action.IMPLEMENTED
    return lease, jobs, executor


@pytest.mark.asyncio
async def test_one_native_turn_completes_one_phase_not_a_role_chain() -> None:
    lease, jobs, executor = setup()
    await RunEngineeringJob(jobs, executor).execute(lease)
    jobs.complete.assert_awaited_once_with(lease, Action.IMPLEMENTED)
    executor.execute.assert_awaited_once_with(lease)
    jobs.block.assert_not_called()


@pytest.mark.asyncio
async def test_revoked_lease_never_starts_model() -> None:
    lease, jobs, executor = setup()
    jobs.heartbeat.return_value = False
    await RunEngineeringJob(jobs, executor).execute(lease)
    executor.execute.assert_not_called()
    jobs.complete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("heartbeat_failure", [False, RuntimeError("database unavailable")])
async def test_lease_loss_or_db_outage_interrupts_before_blocking(
    heartbeat_failure: object,
) -> None:
    lease, jobs, executor = setup()
    interrupted = asyncio.Event()

    async def running(_: PhaseLease) -> Action:
        try:
            await asyncio.Event().wait()
            return Action.IMPLEMENTED
        finally:
            interrupted.set()

    async def block(*_: object) -> None:
        assert interrupted.is_set()

    executor.execute.side_effect = running
    jobs.heartbeat.side_effect = [True, heartbeat_failure]
    jobs.block.side_effect = block
    await RunEngineeringJob(jobs, executor, heartbeat_seconds=0.001).execute(lease)
    assert interrupted.is_set()
    jobs.complete.assert_not_called()
    assert executor.execute.await_count == 1


@pytest.mark.asyncio
async def test_shutdown_cancels_running_operation_without_requeue() -> None:
    lease, jobs, executor = setup()
    started, interrupted = asyncio.Event(), asyncio.Event()

    async def running(_: PhaseLease) -> Action:
        started.set()
        try:
            await asyncio.Event().wait()
            return Action.IMPLEMENTED
        finally:
            interrupted.set()

    executor.execute.side_effect = running
    operation = asyncio.create_task(RunEngineeringJob(jobs, executor).execute(lease))
    await started.wait()
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert interrupted.is_set()
    jobs.block.assert_awaited_once()
    jobs.complete.assert_not_called()


@pytest.mark.asyncio
async def test_budget_block_does_not_reenter_planning_or_retry() -> None:
    lease, jobs, executor = setup()
    executor.execute.side_effect = PhaseBlocked(WaitReason.BUDGET_EXHAUSTED, "Unknown cost")
    await RunEngineeringJob(jobs, executor).execute(lease)
    jobs.block.assert_awaited_once_with(lease, WaitReason.BUDGET_EXHAUSTED, "Unknown cost")
    assert executor.execute.await_count == 1


@pytest.mark.asyncio
async def test_unexpected_error_does_not_persist_secrets() -> None:
    lease, jobs, executor = setup()
    executor.execute.side_effect = ValueError("api_key=secret")
    await RunEngineeringJob(jobs, executor).execute(lease)
    assert "secret" not in str(jobs.block.await_args)
