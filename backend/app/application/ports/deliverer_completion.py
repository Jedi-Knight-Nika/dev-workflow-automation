import types
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Self

from app.domain.jobs import CompletionDirective


@dataclass(frozen=True, slots=True)
class DelivererCompletionCommand:
    job_id: uuid.UUID
    lease_token: uuid.UUID
    result: dict[str, Any]
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class DelivererCompletionContext:
    job_id: uuid.UUID
    task_id: uuid.UUID
    action: str
    job_payload: dict[str, Any]
    outcome: str | None
    data: dict[str, Any]
    manual_takeover: bool


class DelivererCompletionUnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None: ...

    async def begin(
        self, command: DelivererCompletionCommand
    ) -> DelivererCompletionContext | None: ...

    async def finish_during_takeover(self, context: DelivererCompletionContext) -> None: ...

    async def finish_conversation(self, context: DelivererCompletionContext) -> None: ...

    async def apply(
        self, context: DelivererCompletionContext, directive: CompletionDirective
    ) -> None: ...

    async def commit(self) -> None: ...

    async def execute_external_delivery_actions(
        self, context: DelivererCompletionContext
    ) -> None: ...

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None: ...


class DelivererCompletionUnitOfWorkFactory(Protocol):
    def __call__(self) -> DelivererCompletionUnitOfWork: ...
