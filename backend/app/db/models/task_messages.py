from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

from ._base import utcnow


class TaskMessage(Base):
    """Append-only internal conversation attached to a Task."""

    __tablename__ = "task_messages"
    __table_args__ = (
        Index("ix_task_messages_task_id_id", "task_id", "id"),
        Index("ix_task_messages_agent_id", "agent_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), unique=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_agents.id", ondelete="SET NULL")
    )
    author_type: Mapped[str] = mapped_column(String(20))
    author_name: Mapped[str] = mapped_column(String(120))
    author_role: Mapped[str | None] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(30), default="COMMENT")
    body: Mapped[str] = mapped_column(Text)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
