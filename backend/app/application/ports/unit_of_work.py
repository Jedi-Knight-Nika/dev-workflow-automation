import uuid
from typing import Any, Protocol

from app.domain.tasks import Task


class TaskRepository(Protocol):
    async def add(self, task: Task) -> None: ...


class JobRepository(Protocol):
    async def enqueue_intake(self, task: Task, payload: dict[str, Any]) -> uuid.UUID: ...


class EventRepository(Protocol):
    async def add(
        self,
        task_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
        *,
        source: str,
    ) -> None: ...


class UnitOfWork(Protocol):
    tasks: TaskRepository
    jobs: JobRepository
    events: EventRepository

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
