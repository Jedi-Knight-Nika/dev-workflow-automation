import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.application.ports.job_enqueueing import EnqueuedJob


@dataclass(frozen=True, slots=True)
class TaskEventView:
    id: int
    task_id: uuid.UUID
    source: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ValidationView:
    id: uuid.UUID
    provider: str
    kind: str
    name: str
    status: str
    revision: str
    details_url: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewFindingView:
    id: uuid.UUID
    reviewer_job_id: uuid.UUID
    workspace_fingerprint: str
    finding_fingerprint: str | None
    occurrence_count: int
    severity: str
    file_path: str | None
    line: int | None
    message: str
    status: str
    created_at: datetime
    last_seen_at: datetime | None
    resolved_at: datetime | None


class TaskHistoryQueries(Protocol):
    async def jobs(self, task_id: uuid.UUID) -> list[EnqueuedJob]: ...
    async def events(self, task_id: uuid.UUID) -> list[TaskEventView]: ...
    async def validations(self, task_id: uuid.UUID) -> list[ValidationView]: ...
    async def findings(self, task_id: uuid.UUID) -> list[ReviewFindingView]: ...
