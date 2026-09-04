import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import JobRole, JobState, TaskState


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    priority: int = Field(default=3, ge=0, le=5)
    external_key: str | None = Field(default=None, max_length=100)
    enqueue_planning: bool = True


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    external_key: str | None
    title: str
    description: str
    priority: int
    state: TaskState
    current_revision: str | None
    created_at: datetime
    updated_at: datetime


class JobCreate(BaseModel):
    role: JobRole
    action: str = Field(min_length=1, max_length=100)
    priority: int = Field(default=3, ge=0, le=5)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID
    role: JobRole
    action: str
    priority: int
    state: JobState
    attempt: int
    payload: dict[str, Any]
    result: dict[str, Any] | None
    worker_id: str | None
    failure_reason: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: uuid.UUID
    source: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class WorkerResult(BaseModel):
    protocol_version: int = 1
    job_id: uuid.UUID
    task_id: uuid.UUID
    role: JobRole
    result: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
