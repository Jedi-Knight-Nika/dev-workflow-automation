from __future__ import annotations

# Model modules intentionally share this compact SQLAlchemy import vocabulary.
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class WorkerNode(Base):
    __tablename__ = "worker_nodes"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255))
    process_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="ONLINE")
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
