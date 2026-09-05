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


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=3)
    state: Mapped[TaskState] = mapped_column(Enum(TaskState), default=TaskState.NEW)
    current_revision: Mapped[str | None] = mapped_column(String(64))
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL")
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="SET NULL")
    )
    workflow_version: Mapped[int | None] = mapped_column(Integer)
    current_workflow_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    branch_name: Mapped[str | None] = mapped_column(String(255))
    workspace_path: Mapped[str | None] = mapped_column(Text)
    pull_request_number: Mapped[int | None] = mapped_column(Integer)
    pull_request_url: Mapped[str | None] = mapped_column(Text)
    manual_takeover: Mapped[bool] = mapped_column(default=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    project_name: Mapped[str | None] = mapped_column(String(255))
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    estimate: Mapped[float | None] = mapped_column(Numeric(8, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    jobs: Mapped[list[Job]] = relationship(back_populates="task", cascade="all, delete-orphan")
    events: Mapped[list[TaskEvent]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "state", "priority", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    role: Mapped[JobRole] = mapped_column(Enum(JobRole))
    workflow_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_agents.id", ondelete="SET NULL")
    )
    team_workflow_version: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(100))
    priority: Mapped[int] = mapped_column(Integer, default=3)
    state: Mapped[JobState] = mapped_column(Enum(JobState), default=JobState.QUEUED)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    worker_id: Mapped[str | None] = mapped_column(String(200))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    task: Mapped[Task] = relationship(back_populates="jobs")


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (
        UniqueConstraint("source", "external_event_id", name="uq_event_source_external_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(50))
    event_type: Mapped[str] = mapped_column(String(100))
    external_event_id: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    task: Mapped[Task] = relationship(back_populates="events")


class ExternalTaskSnapshot(Base):
    __tablename__ = "external_task_snapshots"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_external_task_provider_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(255))
    identifier: Mapped[str] = mapped_column(String(100))
    assignee_id: Mapped[str | None] = mapped_column(String(255))
    state_id: Mapped[str | None] = mapped_column(String(255))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    synchronized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskMemory(Base):
    __tablename__ = "task_memories"
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    goal: Mapped[str] = mapped_column(Text, default="")
    known_facts: Mapped[list[str]] = mapped_column(JSON, default=list)
    decisions: Mapped[list[str]] = mapped_column(JSON, default=list)
    rejected_approaches: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    invariants: Mapped[list[str]] = mapped_column(JSON, default=list)
    important_files: Mapped[list[str]] = mapped_column(JSON, default=list)
    important_symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    open_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    open_finding_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    resolved_finding_summaries: Mapped[list[str]] = mapped_column(JSON, default=list)
    current_plan_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    current_sha: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AgentCheckpoint(Base):
    __tablename__ = "agent_checkpoints"
    __table_args__ = (Index("ix_checkpoints_task_role_created", "task_id", "role", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), unique=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_agents.id", ondelete="SET NULL")
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    role: Mapped[JobRole] = mapped_column(Enum(JobRole))
    checkpoint_type: Mapped[str] = mapped_column(String(50))
    repository_sha: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    token_estimate: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobContext(Base):
    __tablename__ = "job_contexts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), unique=True
    )
    compiler_version: Mapped[str] = mapped_column(String(30))
    task_memory_version: Mapped[int | None] = mapped_column(Integer)
    repository_sha: Mapped[str | None] = mapped_column(String(64))
    checkpoint_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    plan_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    finding_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    rag_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    estimated_input_tokens: Mapped[int] = mapped_column(Integer)
    compilation_duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkspaceLease(Base):
    __tablename__ = "workspace_leases"
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ValidationRecord(Base):
    __tablename__ = "validation_records"
    __table_args__ = (Index("ix_validation_task_revision", "task_id", "revision"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50), default="github")
    kind: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50))
    revision: Mapped[str] = mapped_column(String(64))
    details_url: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewFinding(Base):
    __tablename__ = "review_findings"
    __table_args__ = (
        Index("ix_review_findings_task_status", "task_id", "status"),
        Index("ix_review_findings_fingerprint", "task_id", "finding_fingerprint"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    reviewer_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    workspace_fingerprint: Mapped[str] = mapped_column(String(64))
    finding_fingerprint: Mapped[str | None] = mapped_column(String(64))
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    severity: Mapped[str] = mapped_column(String(20))
    file_path: Mapped[str | None] = mapped_column(Text)
    line: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
