from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class AccountSettings(Base):
    __tablename__ = "account_settings"
    id: Mapped[str] = mapped_column(String(50), primary_key=True, default="default")
    display_name: Mapped[str] = mapped_column(String(120), default="Local user")
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    date_format: Mapped[str] = mapped_column(String(30), default="YYYY-MM-DD")
    time_format: Mapped[str] = mapped_column(String(10), default="24H")
    default_landing_page: Mapped[str] = mapped_column(String(50), default="dashboard")
    default_task_view: Mapped[str] = mapped_column(String(30), default="board")
    appearance: Mapped[str] = mapped_column(String(20), default="system")
    compact_dashboard: Mapped[bool] = mapped_column(default=False)
    settings_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SettingsAuditEvent(Base):
    __tablename__ = "settings_audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    section: Mapped[str] = mapped_column(String(50))
    old_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    new_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(50), default="dashboard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
