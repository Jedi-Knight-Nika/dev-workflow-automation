from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class ExternalTaskSnapshot(Base):
    __tablename__ = "external_task_snapshots"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_external_task_provider_id"),
        Index("ix_external_task_snapshots_task", "task_id"),
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
