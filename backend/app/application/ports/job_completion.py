import types
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Self


@dataclass(frozen=True, slots=True)
class FailedJobCommand:
    job_id: uuid.UUID
    lease_token: uuid.UUID
    terminal_state: str
    failure: str
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class FailedJobContext:
    job_id: uuid.UUID
    task_id: uuid.UUID
    attempt: int
    manual_takeover: bool
    failure_class: str = "IMPLEMENTATION_FAILURE"


class FailedCompletionUnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None: ...

    async def begin(self, command: FailedJobCommand) -> FailedJobContext | None: ...

    async def schedule_retry(
        self, context: FailedJobContext, delay_seconds: int, max_attempts: int
    ) -> None: ...

    async def exhaust(self, context: FailedJobContext) -> None: ...

    async def finish_during_takeover(self, context: FailedJobContext) -> None: ...

    async def commit(self) -> None: ...

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None: ...


class FailedCompletionUnitOfWorkFactory(Protocol):
    def __call__(self) -> FailedCompletionUnitOfWork: ...
