from typing import Protocol
from uuid import UUID

from app.engineering.domain.controls import LifecycleAction
from app.engineering.domain.task import Task


class TaskLifecycleStore(Protocol):
    async def change(self, task_id: UUID, action: LifecycleAction, *, actor: str) -> Task: ...


class TaskLifecycleUnitOfWorkFactory(Protocol):
    def __call__(self) -> TaskLifecycleStore: ...
