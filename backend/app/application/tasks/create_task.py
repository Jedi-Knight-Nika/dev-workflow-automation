import uuid
from dataclasses import dataclass
from datetime import datetime

from app.application.ports import UnitOfWork
from app.domain.tasks import Task


@dataclass(frozen=True, slots=True)
class CreateTaskCommand:
    title: str
    description: str = ""
    priority: int = 3
    external_key: str | None = None
    repository_id: uuid.UUID | None = None
    enqueue_planning: bool = True
    project_name: str | None = None
    labels: tuple[str, ...] = ()
    estimate: float | None = None
    due_at: datetime | None = None


class CreateTask:
    def __init__(self, unit_of_work: UnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def execute(self, command: CreateTaskCommand) -> Task:
        task = Task.create(
            title=command.title,
            description=command.description,
            priority=command.priority,
            external_key=command.external_key,
            repository_id=command.repository_id,
            project_name=command.project_name,
            labels=command.labels,
            estimate=command.estimate,
            due_at=command.due_at,
        )
        try:
            await self._unit_of_work.tasks.add(task)
            await self._unit_of_work.events.add(
                task.id, "TASK_CREATED", {"title": task.title}, source="api"
            )
            if command.enqueue_planning:
                await self._unit_of_work.jobs.enqueue_intake(task, payload={"source": "dashboard"})
            await self._unit_of_work.commit()
        except Exception:
            await self._unit_of_work.rollback()
            raise
        return task
