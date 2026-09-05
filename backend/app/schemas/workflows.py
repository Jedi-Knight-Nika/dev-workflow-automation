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


class WorkflowNodeRead(BaseModel):
    model_config = ConfigDict(protected_namespaces=("model_dump",))

    id: uuid.UUID
    role: str
    label: str = Field(min_length=1, max_length=100)
    position_x: float
    position_y: float
    enabled: bool = True
    activation_policy: str = "any"
    batch_window_seconds: int = Field(default=0, ge=0, le=300)
    integration_ids: list[uuid.UUID] = Field(default_factory=list)
    repository_ids: list[uuid.UUID] = Field(default_factory=list)
    provider: str = Field(default="openai", pattern="^(openai|anthropic|google)$")
    model: str = Field(default="", max_length=255)
    system_prompt: str = Field(default="", max_length=100_000)
    model_validation_status: str = "NOT_CONFIGURED"
    model_validation_message: str | None = None
    model_validated_at: datetime | None = None
    integration_mode: str = Field(default="webhook", pattern="^(webhook|poll|hybrid|manual)$")
    poll_interval_seconds: int = Field(default=300, ge=60, le=86_400)
    filter_assignee_id: str = Field(default="", max_length=255)
    filter_state_ids: list[str] = Field(default_factory=list)
    integration_sync_status: str = "IDLE"
    integration_sync_error: str | None = None
    integration_last_synced_at: datetime | None = None
    reasoning_effort: str = Field(default="default", pattern="^(default|low|medium|high|max)$")
    max_output_tokens: int | None = Field(default=None, ge=256, le=200_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    timeout_minutes: int = Field(default=60, ge=1, le=720)
    max_retries: int = Field(default=2, ge=0, le=10)
    max_review_cycles: int = Field(default=3, ge=0, le=20)
    context_depth: str = Field(default="normal", pattern="^(low|normal|deep)$")
    rag_retrieval_depth: str = Field(default="normal", pattern="^(low|normal|deep)$")
    fallback_provider: str | None = Field(default=None, pattern="^(openai|anthropic|google)$")
    fallback_model: str | None = Field(default=None, max_length=255)
    agent_id: uuid.UUID | None = None
    node_type: str = Field(
        default="AGENT", pattern="^(AGENT|SYSTEM_GATE|TERMINAL|HUMAN_APPROVAL|EXTERNAL_WAIT)$"
    )
    system_node_type: str | None = None


class WorkflowNodeModelValidationRead(BaseModel):
    node_id: uuid.UUID
    status: str
    message: str | None = None
    validated_at: datetime


class WorkflowEdgeRead(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    outcome: str = "success"
    required: bool = True
    job_type: str | None = Field(default=None, max_length=100)
    internal_task_state: str | None = Field(default=None, max_length=50)
    external_status_key: str | None = Field(default=None, max_length=100)
    priority_override: int | None = Field(default=None, ge=0, le=5)
    configuration: dict[str, object] = Field(default_factory=dict)


class WorkflowGraphRead(BaseModel):
    version: int = Field(ge=0)
    nodes: list[WorkflowNodeRead]
    edges: list[WorkflowEdgeRead]
