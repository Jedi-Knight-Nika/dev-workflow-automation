from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
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

from app.platform.persistence.base import Base, utcnow
from app.platform.scheduling.states import JobState


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('NEW','ACTIVE','WAITING_EXTERNAL','WAITING_HUMAN','PAUSED','FAILED','CANCELLED','MERGED')",
            name="ck_task_status",
        ),
        CheckConstraint(
            "stage IN ('INTAKE','PLANNING','DEVELOPING','VALIDATING','PUBLISHING','REVIEWING','FIXING','MERGING','COMPLETE')",
            name="ck_task_stage",
        ),
        CheckConstraint(
            "requirement_version >= 1 AND lifecycle_version >= 1", name="ck_task_versions"
        ),
        CheckConstraint("priority BETWEEN 0 AND 5", name="ck_task_priority"),
        Index("ix_tasks_status_priority", "status", "priority"),
        Index("ix_tasks_due_at", "due_at"),
        Index("ix_tasks_team_status", "team_id", "status"),
        Index("ix_tasks_repository", "repository_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(24), default="NEW", server_default="NEW")
    stage: Mapped[str] = mapped_column(String(24), default="INTAKE", server_default="INTAKE")
    wait_reason: Mapped[str] = mapped_column(String(40), default="NONE", server_default="NONE")
    requirement_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    lifecycle_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    current_revision: Mapped[str | None] = mapped_column(String(64))
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL")
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    branch_name: Mapped[str | None] = mapped_column(String(255))
    workspace_path: Mapped[str | None] = mapped_column(Text)
    pull_request_number: Mapped[int | None] = mapped_column(Integer)
    pull_request_url: Mapped[str | None] = mapped_column(Text)
    manual_takeover: Mapped[bool] = mapped_column(default=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    project_name: Mapped[str | None] = mapped_column(String(255))
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    estimate: Mapped[float | None] = mapped_column(Numeric(8, 2))
    progress_fingerprint: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    no_progress_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    jobs: Mapped[list[Job]] = relationship(back_populates="task", cascade="all, delete-orphan")
    events: Mapped[list[TaskEvent]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    repository_scopes: Mapped[list[TaskRepositoryScope]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskRepositoryScope(Base):
    """Repository selected from the owning Team's available execution scope."""

    __tablename__ = "task_repository_scopes"
    __table_args__ = (
        UniqueConstraint("task_id", "repository_id", name="uq_task_repository_scope"),
        Index("ix_task_repository_scopes_repository", "repository_id"),
        Index("ix_task_repository_scopes_task", "task_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="RESTRICT")
    )
    selected_by: Mapped[str] = mapped_column(String(30), default="routing")
    reason: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    is_primary: Mapped[bool] = mapped_column(default=False)
    workspace_path: Mapped[str | None] = mapped_column(Text)
    branch_name: Mapped[str | None] = mapped_column(String(255))
    base_revision: Mapped[str | None] = mapped_column(String(64))
    current_revision: Mapped[str | None] = mapped_column(String(64))
    changed: Mapped[bool] = mapped_column(default=False)
    pull_request_number: Mapped[int | None] = mapped_column(Integer)
    pull_request_url: Mapped[str | None] = mapped_column(Text)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merge_commit_sha: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    task: Mapped[Task] = relationship(back_populates="repository_scopes")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "state", "priority", "created_at"),
        Index("ix_jobs_retry_not_before", "retry_not_before"),
        Index("ix_jobs_task", "task_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
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
        Index("ix_task_events_task", "task_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(50))
    event_type: Mapped[str] = mapped_column(String(100))
    external_event_id: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    task: Mapped[Task] = relationship(back_populates="events")
