from __future__ import annotations

# Model modules intentionally share this compact SQLAlchemy import vocabulary.
# ruff: noqa: F401
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.operational_states import IndexStatus, IntegrationStatus, JobRole, JobState
from app.domain.tasks import TaskState

from ._base import utcnow


class ExecutionPolicy(Base):
    __tablename__ = "execution_policies"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), unique=True
    )
    mode: Mapped[str] = mapped_column(String(30), default="AUTONOMOUS")
    settings: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    approved_hosts: Mapped[list[str]] = mapped_column(JSON, default=list)
    max_command_timeout_seconds: Mapped[int] = mapped_column(Integer, default=1200)
    max_output_bytes: Mapped[int] = mapped_column(Integer, default=1_000_000)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_agents.id", ondelete="SET NULL")
    )
    tool: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(120))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    arguments_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(30), default="PENDING")
    resolution_scope: Mapped[str | None] = mapped_column(String(30))
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ToolExecutionEvent(Base):
    __tablename__ = "tool_execution_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    worker_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("worker_runs.id", ondelete="SET NULL")
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_agents.id", ondelete="SET NULL")
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    tool: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(120))
    decision: Mapped[str] = mapped_column(String(30))
    policy_rule: Mapped[str] = mapped_column(String(255))
    arguments_sanitized: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkerRun(Base):
    __tablename__ = "worker_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    role: Mapped[JobRole] = mapped_column(Enum(JobRole))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(255))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 6))
    duration_ms: Mapped[int] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_agents.id", ondelete="SET NULL")
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    role_version: Mapped[int | None] = mapped_column(Integer)
    effective_permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    effective_knowledge_scope: Mapped[list[str]] = mapped_column(JSON, default=list)
    effective_runtime_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    effective_runtime_config_hash: Mapped[str | None] = mapped_column(String(64))
    model_capability_version: Mapped[str | None] = mapped_column(String(30))
    agent_config_version: Mapped[int | None] = mapped_column(Integer)
    strategy_version: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkerNode(Base):
    __tablename__ = "worker_nodes"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255))
    process_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="ONLINE")
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
