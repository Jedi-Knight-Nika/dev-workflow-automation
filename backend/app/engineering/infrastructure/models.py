import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class TaskPhaseRun(Base):
    __tablename__ = "task_phase_runs"
    __table_args__ = (Index("ix_phase_task_started", "task_id", "started_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(255))
    wait_reason: Mapped[str] = mapped_column(String(40), default="NONE")
    requirement_version: Mapped[int] = mapped_column(default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ValidationRun(Base):
    __tablename__ = "validation_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    head_sha: Mapped[str] = mapped_column(String(64))
    requirement_version: Mapped[int]
    command: Mapped[list[str]] = mapped_column(JSON)
    exit_code: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(24))
    output_tail: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewCycle(Base):
    __tablename__ = "review_cycles"
    __table_args__ = (
        UniqueConstraint("task_id", "external_event_id", name="uq_review_cycle_event"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    external_event_id: Mapped[str] = mapped_column(String(255))
    head_sha: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(255))
    decision: Mapped[str] = mapped_column(String(40))
    feedback: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
