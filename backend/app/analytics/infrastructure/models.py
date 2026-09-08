from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class TaskForecast(Base):
    __tablename__ = "task_forecasts"
    __table_args__ = (
        UniqueConstraint("task_id", "forecast_version", name="uq_task_forecast_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    forecast_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model_kind: Mapped[str] = mapped_column(String(40), default="statistical-quantiles")
    sample_count: Mapped[int]
    confidence: Mapped[str] = mapped_column(String(16))
    estimates: Mapped[dict[str, Any]] = mapped_column(JSON)
    actuals: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
