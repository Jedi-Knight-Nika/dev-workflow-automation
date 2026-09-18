import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime

from app.engineering.application.ports.unit_of_work import UnitOfWork
from app.engineering.domain.task import Task


class CreationConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreateTaskCommand:
    title: str
    description: str = ""
    priority: int = 3
    external_key: str | None = None
    repository_id: uuid.UUID | None = None
    start_work: bool = False
    project_name: str | None = None
    labels: tuple[str, ...] = ()
    estimate: float | None = None
    due_at: datetime | None = None
    team_id: uuid.UUID | None = None
    request_id: uuid.UUID | None = None


class CreateTask:
    def __init__(self, unit_of_work: UnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def execute(self, command: CreateTaskCommand) -> Task:
        payload = asdict(command)
        payload.pop("request_id")
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
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
            if command.request_id is not None:
                existing = await self._unit_of_work.tasks.find_creation(
                    command.request_id, fingerprint
                )
                if existing is not None:
                    await self._unit_of_work.commit()
                    return existing
            await self._unit_of_work.tasks.add(task)
            if command.team_id is not None:
                await self._unit_of_work.assignments.assign(task.id, command.team_id)
                task.team_id = command.team_id
            await self._unit_of_work.events.add(
                task.id, "TASK_CREATED", {"title": task.title}, source="api"
            )
            if command.start_work:
                await self._unit_of_work.execution.start(task)
            if command.request_id is not None:
                await self._unit_of_work.tasks.remember_creation(
                    command.request_id, fingerprint, task.id
                )
            await self._unit_of_work.commit()
        except Exception:
            await self._unit_of_work.rollback()
            raise
        return task
