"""Coordination records reuse TaskMessage, AIRun and the engineering job queue."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class CoordinatorEvent(Base):
    __tablename__ = "coordinator_events"
    __table_args__ = (
        UniqueConstraint("provider", "delivery_key", name="uq_coordinator_delivery"),
        Index("ix_coordinator_event_due", "status", "available_at"),
        Index("ix_coordinator_event_task", "task_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(30))
    delivery_key: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(120))
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED")
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("coordinator_runs.id", ondelete="SET NULL")
    )
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CoordinatorRun(Base):
    __tablename__ = "coordinator_runs"
    __table_args__ = (Index("ix_coordinator_run_task", "task_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="CLAIMED")
    requirement_revision: Mapped[int]
    lifecycle_revision: Mapped[int]
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CoordinatorAction(Base):
    __tablename__ = "coordinator_actions"
    __table_args__ = (Index("ix_coordinator_action_status", "status", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("coordinator_runs.id", ondelete="CASCADE"), unique=True
    )
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    provider_effect_ref: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HumanRequest(Base):
    __tablename__ = "human_requests"
    __table_args__ = (Index("ix_human_request_open", "task_id", "status"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("coordinator_runs.id", ondelete="CASCADE"), unique=True
    )
    category: Mapped[str] = mapped_column(String(32), default="CLARIFICATION")
    question: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    choices: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    requirement_revision: Mapped[int]
    lifecycle_revision: Mapped[int]
    answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
