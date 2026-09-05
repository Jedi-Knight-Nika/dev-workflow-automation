from __future__ import annotations

# Schema modules share a small validation vocabulary.
# ruff: noqa: F401
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.domain.agents import AgentRole
from app.domain.operational_states import IndexStatus, IntegrationStatus, JobRole, JobState
from app.domain.tasks import TaskState


class WorkerResult(BaseModel):
    protocol_version: int = 1
    job_id: uuid.UUID
    task_id: uuid.UUID
    role: JobRole
    result: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class WorkerNodeRead(BaseModel):
    id: str
    hostname: str
    process_id: int
    status: str
    online: bool
    capabilities: list[str]
    started_at: datetime
    last_heartbeat: datetime
    stopped_at: datetime | None


class ValidationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    provider: str
    kind: str
    name: str
    status: str
    revision: str
    details_url: str | None
    created_at: datetime


class ReviewFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
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
