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


class ExecutionPolicyWrite(BaseModel):
    mode: str = Field(pattern="^(CONSERVATIVE|AUTONOMOUS|CUSTOM)$")
    settings: dict[str, str] = Field(default_factory=dict)
    approved_hosts: list[str] = Field(default_factory=list, max_length=100)
    max_command_timeout_seconds: int = Field(default=1200, ge=10, le=7200)
    max_output_bytes: int = Field(default=1_000_000, ge=1024, le=5_000_000)


class ExecutionPolicyRead(ExecutionPolicyWrite):
    isolation_level: str
    execution_environment: str


class ApprovalResolution(BaseModel):
    resolved_by: str = Field(default="local-user", min_length=1, max_length=255)
    scope: str = Field(default="ONCE", pattern="^(ONCE|TASK)$")
