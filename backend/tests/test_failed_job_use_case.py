import types
import uuid
from datetime import UTC, datetime
from typing import Self

import pytest

from app.application.jobs import CompleteFailedJob
from app.application.ports.job_completion import FailedJobCommand, FailedJobContext
from app.domain.jobs import RetryPolicy


class FakeFailureUnitOfWork:
    def __init__(self, context: FailedJobContext | None) -> None:
        self.context = context
        self.retry: tuple[int, int] | None = None
        self.exhausted = False
        self.takeover = False
        self.committed = False
        self.synchronized = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        return None

    async def begin(self, _command: FailedJobCommand) -> FailedJobContext | None:
        return self.context

    async def schedule_retry(
        self, _context: FailedJobContext, delay_seconds: int, max_attempts: int
    ) -> None:
        self.retry = (delay_seconds, max_attempts)

    async def exhaust(self, _context: FailedJobContext) -> None:
        self.exhausted = True

    async def finish_during_takeover(self, _context: FailedJobContext) -> None:
        self.takeover = True

    async def commit(self) -> None:
        self.committed = True

    async def synchronize_tracker(self, _task_id: uuid.UUID) -> None:
        self.synchronized = True


def command() -> FailedJobCommand:
    return FailedJobCommand(
        uuid.uuid4(), uuid.uuid4(), "TIMED_OUT", "Worker timed out", datetime.now(UTC)
    )


@pytest.mark.asyncio
async def test_failed_job_use_case_schedules_bounded_retry() -> None:
    unit = FakeFailureUnitOfWork(FailedJobContext(uuid.uuid4(), uuid.uuid4(), 2, False))
    handler = CompleteFailedJob(lambda: unit, RetryPolicy(3, 5))  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.retry == (10, 3)
    assert unit.committed and unit.synchronized
    assert not unit.exhausted


@pytest.mark.asyncio
async def test_failed_job_use_case_escalates_after_retry_exhaustion() -> None:
    unit = FakeFailureUnitOfWork(FailedJobContext(uuid.uuid4(), uuid.uuid4(), 3, False))
    handler = CompleteFailedJob(lambda: unit, RetryPolicy(3, 5))  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.exhausted and unit.committed and unit.synchronized
    assert unit.retry is None


@pytest.mark.asyncio
async def test_failed_job_during_takeover_preserves_manual_control() -> None:
    unit = FakeFailureUnitOfWork(FailedJobContext(uuid.uuid4(), uuid.uuid4(), 1, True))
    handler = CompleteFailedJob(lambda: unit, RetryPolicy(3, 5))  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.takeover and unit.committed and unit.synchronized
    assert unit.retry is None and not unit.exhausted


@pytest.mark.asyncio
async def test_stale_failed_worker_result_is_ignored_without_commit() -> None:
    unit = FakeFailureUnitOfWork(None)
    handler = CompleteFailedJob(lambda: unit, RetryPolicy(3, 5))  # type: ignore[arg-type]

    assert not await handler.execute(command())
    assert not unit.committed and not unit.synchronized
