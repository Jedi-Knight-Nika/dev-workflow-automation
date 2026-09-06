import types
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Self


@dataclass(frozen=True, slots=True)
class TesterCompletionCommand:
    job_id: uuid.UUID
    lease_token: uuid.UUID
    result: dict[str, Any]
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class TesterCompletionContext:
    job_id: uuid.UUID
    task_id: uuid.UUID
    outcome: str | None
    result: dict[str, Any]
    manual_takeover: bool


class TesterCompletionUnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None: ...
    async def begin(self, command: TesterCompletionCommand) -> TesterCompletionContext | None: ...
    async def finish_during_takeover(self, context: TesterCompletionContext) -> None: ...
    async def apply(self, context: TesterCompletionContext) -> None: ...
    async def commit(self) -> None: ...
    async def synchronize_tracker(self, task_id: uuid.UUID) -> None: ...


class TesterCompletionUnitOfWorkFactory(Protocol):
    def __call__(self) -> TesterCompletionUnitOfWork: ...
