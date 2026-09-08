from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.engineering.domain.lifecycle import TaskStatus
from app.platform.scheduling.states import JobState


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    priority: int = Field(default=3, ge=0, le=5)
    external_key: str | None = Field(default=None, max_length=100)
    start_work: bool = False
    repository_id: uuid.UUID | None = None
    project_name: str | None = Field(default=None, max_length=255)
    labels: list[str] = Field(default_factory=list, max_length=50)
    estimate: float | None = Field(default=None, ge=0, le=1000000)
    due_at: datetime | None = None


class ExternalTaskRead(BaseModel):
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
    labels: list[str]
    estimate: float | None
    due_date: str | None
    provider_created_at: str | None
    provider_updated_at: str | None
    raw_payload: dict[str, Any]


class TaskRepositoryScopeRead(BaseModel):
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


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    external_key: str | None
    title: str
    description: str
    priority: int
    status: TaskStatus
    stage: str
    wait_reason: str
    lifecycle_version: int
    requirement_version: int
    current_revision: str | None
    repository_id: uuid.UUID | None
    branch_name: str | None
    workspace_path: str | None
    pull_request_number: int | None
    pull_request_url: str | None
    manual_takeover: bool
    source: ExternalTaskRead | None = None
    repository_name: str | None = None
    due_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    project_name: str | None = None
    labels: list[str] = Field(default_factory=list)
    estimate: float | None = None
    repository_scopes: list[TaskRepositoryScopeRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID
    action: str
    priority: int
    state: JobState
    attempt: int
    payload: dict[str, Any]
    result: dict[str, Any] | None
    worker_id: str | None
    failure_reason: str | None
    retry_not_before: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TaskRoleMetricsRead(BaseModel):
    role: str
    provider: str
    model: str
    attempts: int
    input_tokens: int
    output_tokens: int
    duration_ms: int


class TaskMetricsRead(BaseModel):
    attempts: int
    input_tokens: int
    output_tokens: int
    missing_usage_attempts: int
    duration_ms: int
    estimated_cost_usd: float | None
    roles: list[TaskRoleMetricsRead]
    native_turns: int = 0


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: uuid.UUID
    source: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class TaskMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    reply_to_id: int | None = Field(default=None, ge=1)


class TaskMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: uuid.UUID
    job_id: uuid.UUID | None
    reply_to_id: int | None
    author_type: str
    author_name: str
    author_role: str | None
    kind: str
    body: str
    context: dict[str, Any]
    created_at: datetime


class TaskMessagePageRead(BaseModel):
    items: list[TaskMessageRead]
    next_before_id: int | None
