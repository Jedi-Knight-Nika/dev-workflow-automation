import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.engineering.application.ports.job_enqueueing import EnqueuedJob


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
    exit_code: int | None = None
    output_tail: str = ""
    finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NativeRunView:
    id: uuid.UUID
    role_kind: str
    provider: str
    model: str
    harness: str | None
    status: str
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cost_usd: str | None
    usage_complete: bool
    artifact: str | None
    failure_code: str | None
    started_at: datetime
    finished_at: datetime | None
    requirement_version: int


@dataclass(frozen=True, slots=True)
class LiveExecutionView:
    id: uuid.UUID
    role_kind: str
    provider: str
    model: str
    harness: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    telemetry: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class TaskRoleMetricsView:
    role: str
    provider: str
    model: str
    attempts: int
    input_tokens: int
    output_tokens: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class TaskMetricsView:
    attempts: int
    input_tokens: int
    output_tokens: int
    missing_usage_attempts: int
    duration_ms: int
    estimated_cost_usd: float | None
    roles: tuple[TaskRoleMetricsView, ...]
    native_turns: int = 0


class TaskHistoryQueries(Protocol):
    async def runs(self, task_id: uuid.UUID) -> list[NativeRunView]: ...
    async def live_execution(self, task_id: uuid.UUID) -> LiveExecutionView | None: ...
    async def jobs(self, task_id: uuid.UUID) -> list[EnqueuedJob]: ...
    async def events(self, task_id: uuid.UUID) -> list[TaskEventView]: ...
    async def validations(self, task_id: uuid.UUID) -> list[ValidationView]: ...
    async def metrics(self, task_id: uuid.UUID) -> TaskMetricsView: ...
