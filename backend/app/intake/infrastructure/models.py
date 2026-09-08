import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class LocalModelRun(Base):
    """Local compute is measured separately, never added to paid API tokens."""

    __tablename__ = "local_model_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24))
    duration_ms: Mapped[int]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
