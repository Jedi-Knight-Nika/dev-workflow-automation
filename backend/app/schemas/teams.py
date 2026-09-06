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


class TeamWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    enabled: bool = True
    max_concurrent_tasks: int = Field(default=1, ge=1, le=32)
    repository_ids: list[uuid.UUID] = Field(default_factory=list)


class RoleWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str
    description: str = Field(default="", max_length=4000)
    system_instructions: str = Field(default="", max_length=100_000)
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    allowed_results: list[str] = Field(default_factory=list)
    knowledge_collection_ids: list[uuid.UUID] = Field(default_factory=list)
    default_provider: str | None = None
    default_model: str | None = Field(default=None, max_length=255)
    default_reasoning_effort: str = "default"
    default_timeout_minutes: int = Field(default=30, ge=1, le=720)
    default_max_retries: int = Field(default=2, ge=0, le=10)
    enabled: bool = True


class RoleRead(RoleWrite):
    id: uuid.UUID
    built_in: bool
    version: int
    active_agents: int
    inactive_agents: int
    total_agents: int
    created_at: datetime
    updated_at: datetime


class RoleClone(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TeamRead(TeamWrite):
    id: uuid.UUID
    queued_tasks: int
    running_tasks: int
    completed_tasks: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    created_at: datetime
    updated_at: datetime


class TaskAssignmentCreate(BaseModel):
    task_id: uuid.UUID
    reason: str = Field(default="manual", max_length=500)


class TaskAssignmentRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    team_id: uuid.UUID
    status: str
    queue_position: int
    reason: str
    assigned_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
