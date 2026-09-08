from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow
from app.platform.scheduling.states import IntegrationStatus


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (
        Index("ix_integrations_sync_due", "provider_name", "sync_status", "last_synced_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_type: Mapped[str] = mapped_column(String(50))
    provider_name: Mapped[str] = mapped_column(String(50), unique=True)
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(IntegrationStatus), default=IntegrationStatus.DISCONNECTED
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    encrypted_credentials: Mapped[bytes | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(Text)
    sync_status: Mapped[str] = mapped_column(String(30), default="IDLE")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    @property
    def has_credentials(self) -> bool:
        return self.encrypted_credentials is not None
