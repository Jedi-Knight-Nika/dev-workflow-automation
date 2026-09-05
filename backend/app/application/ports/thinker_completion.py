import types
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Self

from app.domain.jobs import CompletionDirective


@dataclass(frozen=True, slots=True)
class ThinkerCompletionCommand:
    job_id: uuid.UUID
    lease_token: uuid.UUID
    result: dict[str, Any]
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class ThinkerCompletionContext:
    job_id: uuid.UUID
    task_id: uuid.UUID
    outcome: str | None
    data: dict[str, Any]
    manual_takeover: bool


class ThinkerCompletionUnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None: ...

    async def begin(self, command: ThinkerCompletionCommand) -> ThinkerCompletionContext | None: ...
    async def finish_during_takeover(self, context: ThinkerCompletionContext) -> None: ...
    async def apply(
        self, context: ThinkerCompletionContext, directive: CompletionDirective
    ) -> None: ...
    async def commit(self) -> None: ...
    async def synchronize_tracker(self, task_id: uuid.UUID) -> None: ...


class ThinkerCompletionUnitOfWorkFactory(Protocol):
    def __call__(self) -> ThinkerCompletionUnitOfWork: ...
