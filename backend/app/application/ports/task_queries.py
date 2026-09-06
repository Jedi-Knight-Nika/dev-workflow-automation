import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from app.domain.tasks import Task, TaskState


@dataclass(frozen=True, slots=True)
class TaskListFilters:
    search: str | None = None
    states: tuple[TaskState, ...] = ()
    provider: str | None = None
    repository_id: uuid.UUID | None = None
    priorities: tuple[int, ...] = ()
    created_from: datetime | None = None
    created_to: datetime | None = None
    due_from: datetime | None = None
    due_to: datetime | None = None
    updated_from: datetime | None = None
    updated_to: datetime | None = None
    assignee: str | None = None
    team: str | None = None
    project: str | None = None
    label: str | None = None
    provider_state: str | None = None
    assigned_team_id: uuid.UUID | None = None
    unassigned: bool = False
    sort: Literal["priority", "created", "updated", "due"] = "priority"
    direction: Literal["asc", "desc"] = "asc"


@dataclass(frozen=True, slots=True)
class ExternalTaskView:
    provider: str
    external_id: str
    identifier: str
    url: str | None
    state_id: str | None
    state_name: str | None
    assignee_id: str | None
    assignee_name: str | None
    assignee_email: str | None
    creator_name: str | None
    team_name: str | None
    team_key: str | None
    project_name: str | None
    labels: tuple[str, ...]
    estimate: float | None
    due_date: str | None
    provider_created_at: str | None
    provider_updated_at: str | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TaskRepositoryScopeView:
    repository_id: uuid.UUID
    repository_name: str
    selected_by: str
    reason: str
    confidence: float | None
    is_primary: bool
    changed: bool
    branch_name: str | None
    current_revision: str | None
    pull_request_number: int | None
    pull_request_url: str | None


@dataclass(frozen=True, slots=True)
class TaskView:
    task: Task
    source: ExternalTaskView | None
    repository_name: str | None
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    project_name: str | None = None
    labels: tuple[str, ...] = ()
    estimate: float | None = None
    repository_scopes: tuple[TaskRepositoryScopeView, ...] = ()


class TaskQueries(Protocol):
    async def list(self, limit: int, filters: TaskListFilters) -> list[TaskView]: ...
    async def get(self, task_id: uuid.UUID) -> TaskView | None: ...
