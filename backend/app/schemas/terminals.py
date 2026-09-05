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


class TerminalOpen(BaseModel):
    node_id: uuid.UUID | None = None
    cols: int = Field(default=120, ge=40, le=300)
    rows: int = Field(default=32, ge=10, le=100)


class TerminalAccessRead(BaseModel):
    session_id: uuid.UUID
    token: str
    status: str
    cols: int
    rows: int
