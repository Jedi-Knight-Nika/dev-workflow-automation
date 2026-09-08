from uuid import UUID

from app.engineering.application.ports.task_lifecycle import TaskLifecycleUnitOfWorkFactory
from app.engineering.domain.controls import LifecycleAction
from app.engineering.domain.task import Task


class TaskNotFound(Exception):
    pass


class ChangeTaskLifecycle:
    def __init__(self, factory: TaskLifecycleUnitOfWorkFactory) -> None:
        self._factory = factory

    async def execute(self, task_id: UUID, action: LifecycleAction) -> Task:
        try:
            return await self._factory().change(task_id, action, actor="user:ticket-control")
        except LookupError as exc:
            raise TaskNotFound("Task not found") from exc
