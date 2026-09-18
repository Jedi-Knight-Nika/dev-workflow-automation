import uuid
from typing import Any, Protocol

from app.engineering.domain.task import Task


class TaskRepository(Protocol):
    async def add(self, task: Task) -> None: ...

    async def find_creation(self, request_id: uuid.UUID, fingerprint: str) -> Task | None: ...

    async def remember_creation(
        self, request_id: uuid.UUID, fingerprint: str, task_id: uuid.UUID
    ) -> None: ...


class TaskAssignment(Protocol):
    async def assign(self, task_id: uuid.UUID, team_id: uuid.UUID) -> None: ...


class TaskExecution(Protocol):
    async def start(self, task: Task) -> None: ...


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
    execution: TaskExecution
    events: EventRepository
    assignments: TaskAssignment

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
