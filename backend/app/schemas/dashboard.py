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

from .tasks import JobRead


class DashboardActivityRead(BaseModel):
    active_job: JobRead | None
    queued_jobs: list[JobRead]
