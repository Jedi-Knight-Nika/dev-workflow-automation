from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_activity_source"),
        Index("ix_activity_time", "occurred_at", "sequence"),
        Index("ix_activity_task_time", "task_id", "occurred_at", "sequence"),
        Index(
            "ix_activity_references",
            "source_references",
            postgresql_using="gin",
            postgresql_ops={"source_references": "jsonb_path_ops"},
        ),
        Index(
            "ix_activity_file_pending",
            "file_retry_at",
            "sequence",
            postgresql_where=text("kind = 'VALIDATION_PASSED'"),
        ),
    )
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(100))
    detail_level: Mapped[int] = mapped_column(default=1)
    actor_type: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(120))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str] = mapped_column(String(200))
    correlation_id: Mapped[UUID | None]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    references: Mapped[list[dict[str, str]]] = mapped_column(
        "source_references", JSONB, default=list, server_default="[]"
    )
    projector_version: Mapped[int] = mapped_column(default=1)
    file_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_status: Mapped[str | None] = mapped_column(String(24))
    file_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    file_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityFileChange(Base):
    __tablename__ = "activity_file_changes"
    __table_args__ = (Index("ix_activity_files_event", "event_sequence"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_sequence: Mapped[int] = mapped_column(
        ForeignKey("activity_events.sequence", ondelete="CASCADE")
    )
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    operation: Mapped[str] = mapped_column(String(1))
    path: Mapped[str] = mapped_column(String(1000))
    previous_path: Mapped[str | None] = mapped_column(String(1000))
    lines_added: Mapped[int | None]
    lines_deleted: Mapped[int | None]


class ActivityProjectionState(Base):
    __tablename__ = "activity_projection_state"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    caught_up: Mapped[bool] = mapped_column(default=False)
