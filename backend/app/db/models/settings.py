from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

from ._base import utcnow


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

    default_provider_id: Mapped[str | None] = mapped_column(String(50))
    default_model: Mapped[str | None] = mapped_column(String(255))
    default_reasoning_level: Mapped[str] = mapped_column(String(20), default="medium")
    default_max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    provider_failure_behavior: Mapped[str] = mapped_column(String(40), default="PAUSE_AND_NOTIFY")
    structured_output_retry_limit: Mapped[int] = mapped_column(Integer, default=2)

    default_execution_mode: Mapped[str] = mapped_column(String(30), default="AUTONOMOUS")
    default_worker_runtime: Mapped[str] = mapped_column(String(30), default="LOCAL_PROCESS")
    max_concurrent_workers: Mapped[int] = mapped_column(Integer, default=1)
    default_job_timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600)

    default_merge_policy: Mapped[str] = mapped_column(String(30), default="REQUIRE_HUMAN")
    default_unknown_network_policy: Mapped[str] = mapped_column(String(30), default="REQUIRE_HUMAN")
    default_dependency_install_policy: Mapped[str] = mapped_column(String(30), default="ALLOW")
    default_push_task_branch_policy: Mapped[str] = mapped_column(String(30), default="ALLOW")

    auto_index_repositories: Mapped[bool] = mapped_column(default=True)
    incremental_index_after_merge: Mapped[bool] = mapped_column(default=True)
    index_source_code: Mapped[bool] = mapped_column(default=True)
    index_tests: Mapped[bool] = mapped_column(default=True)
    index_documentation: Mapped[bool] = mapped_column(default=True)
    ignore_generated_files: Mapped[bool] = mapped_column(default=True)
    context_strategy: Mapped[str] = mapped_column(String(20), default="BALANCED")

    completed_workspace_retention_days: Mapped[int] = mapped_column(Integer, default=7)
    failed_workspace_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    worker_log_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    audit_event_retention_days: Mapped[int] = mapped_column(Integer, default=90)
    monthly_cost_warning: Mapped[float | None] = mapped_column(Numeric(14, 2))
    monthly_cost_hard_stop: Mapped[float | None] = mapped_column(Numeric(14, 2))

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
