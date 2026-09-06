from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

from ._base import utcnow


class HealthState(Base):
    __tablename__ = "health_states"
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", name="uq_health_resource"),
        Index("ix_health_probe", "circuit_state", "next_probe_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="HEALTHY")
    circuit_state: Mapped[str] = mapped_column(String(20), default="CLOSED")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_class: Mapped[str | None] = mapped_column(String(80))
    failure_fingerprint: Mapped[str | None] = mapped_column(String(255))
    probe_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class FailureEvent(Base):
    __tablename__ = "failure_events"
    __table_args__ = (
        Index("ix_failure_events_job_created", "job_id", "created_at"),
        Index("ix_failure_events_fingerprint", "fingerprint"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    resource_type: Mapped[str | None] = mapped_column(String(40))
    resource_id: Mapped[str | None] = mapped_column(String(255))
    failure_class: Mapped[str] = mapped_column(String(80))
    fingerprint: Mapped[str] = mapped_column(String(255))
    error_code: Mapped[str | None] = mapped_column(String(100))
    safe_message: Mapped[str] = mapped_column(Text)
    technical_details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    retryable: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobRetryState(Base):
    __tablename__ = "job_retry_states"
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    provider_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    integration_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    worker_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    protocol_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    engineering_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_fingerprint: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
