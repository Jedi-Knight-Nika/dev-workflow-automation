from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TeamWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    enabled: bool = True
    max_concurrent_tasks: int = Field(default=1, ge=1, le=32)
    repository_ids: list[uuid.UUID] = Field(default_factory=list)


class TeamRead(TeamWrite):
    execution_paused: bool
    id: uuid.UUID
    queued_tasks: int
    running_tasks: int
    completed_tasks: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float | None
    created_at: datetime
    updated_at: datetime


class TaskAssignmentCreate(BaseModel):
    task_id: uuid.UUID
    reason: str = Field(default="manual", max_length=500)
    start_work: bool = False


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


class WakeTeamRead(BaseModel):
    recovered_jobs: int
    created_jobs: int
    queued_jobs: int
    running_jobs: int
    missing_repository_tasks: int


class ShutdownTeamRead(BaseModel):
    cancelled_jobs: int
    paused_tasks: int
