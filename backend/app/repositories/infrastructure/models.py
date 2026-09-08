from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("provider", "external_repo_id", name="uq_repository_external"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), default="github")
    external_repo_id: Mapped[str] = mapped_column(String(255))
    owner: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    clone_url: Mapped[str] = mapped_column(Text)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    enabled: Mapped[bool] = mapped_column(default=True)
    latest_sha: Mapped[str | None] = mapped_column(String(64))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
