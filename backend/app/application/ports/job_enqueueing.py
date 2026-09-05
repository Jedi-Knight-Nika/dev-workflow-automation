import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class EnqueueTaskNotFound(Exception):
    pass


class EnqueueTaskConflict(Exception):
    pass


@dataclass(frozen=True, slots=True)
class EnqueueJobCommand:
    task_id: uuid.UUID
    role: str
    action: str
    priority: int
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EnqueuedJob:
    id: uuid.UUID
    task_id: uuid.UUID
    role: str
    action: str
    priority: int
    state: str
    attempt: int
    payload: dict[str, Any]
    result: dict[str, Any] | None
    worker_id: str | None
    failure_reason: str | None
    retry_not_before: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobEnqueueWorkflow(Protocol):
    async def enqueue(self, command: EnqueueJobCommand) -> EnqueuedJob: ...
