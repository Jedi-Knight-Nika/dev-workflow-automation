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


class AgentConfigUpdate(BaseModel):
    enabled: bool = True
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(max_length=255)
    configuration: dict[str, Any] = Field(default_factory=dict)


class AgentConfigRead(AgentConfigUpdate):
    model_config = ConfigDict(from_attributes=True)
    role: AgentRole
    updated_at: datetime
    status: str = "READY"
    active_jobs: int = 0
    total_runs: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_estimated_cost_usd: float = 0
    last_run_at: datetime | None = None
    last_duration_ms: int | None = None
    last_provider: str | None = None
    last_model: str | None = None
    active_task_id: uuid.UUID | None = None
    active_task_manual_takeover: bool = False
    active_task_has_workspace: bool = False


class AgentKnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=20, max_length=500_000)


class AgentKnowledgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: AgentRole
    title: str
    chunk_count: int
    created_at: datetime
