import types
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Self

from app.domain.jobs import CompletionDirective


@dataclass(frozen=True, slots=True)
class ReviewerCompletionCommand:
    job_id: uuid.UUID
    lease_token: uuid.UUID
    result: dict[str, Any]
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewerCompletionContext:
    job_id: uuid.UUID
    task_id: uuid.UUID
    action: str
    outcome: str | None
    data: dict[str, Any]
    result: dict[str, Any]
    repeat_count: int
    manual_takeover: bool


class ReviewerCompletionUnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None: ...
    async def begin(
        self, command: ReviewerCompletionCommand
    ) -> ReviewerCompletionContext | None: ...
    async def finish_during_takeover(self, context: ReviewerCompletionContext) -> None: ...
    async def apply(
        self, context: ReviewerCompletionContext, directive: CompletionDirective
    ) -> bool: ...
    async def commit(self) -> None: ...
    async def publish(self, task_id: uuid.UUID) -> None: ...
    async def synchronize_tracker(self, task_id: uuid.UUID) -> None: ...


class ReviewerCompletionUnitOfWorkFactory(Protocol):
    def __call__(self) -> ReviewerCompletionUnitOfWork: ...
