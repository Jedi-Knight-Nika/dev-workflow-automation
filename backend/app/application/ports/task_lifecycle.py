import types
import uuid
from dataclasses import dataclass
from typing import Protocol, Self

from app.domain.tasks import LifecycleDirective, Task, TaskState


class WorkspaceRefreshUnavailable(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TaskLifecycleContext:
    task_id: uuid.UUID
    state: TaskState
    manual_takeover: bool
    has_pull_request: bool
    has_workspace: bool


class TaskLifecycleUnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None: ...
    async def load(self, task_id: uuid.UUID) -> TaskLifecycleContext | None: ...
    async def refresh_workspace(self, task_id: uuid.UUID) -> tuple[str, str]: ...
    async def apply(
        self,
        context: TaskLifecycleContext,
        directive: LifecycleDirective,
        *,
        revision: str | None,
        workspace_fingerprint: str | None,
    ) -> Task: ...
    async def commit(self) -> None: ...


class TaskLifecycleUnitOfWorkFactory(Protocol):
    def __call__(self) -> TaskLifecycleUnitOfWork: ...
