import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class DeveloperSession(Base):
    __tablename__ = "developer_sessions"
    __table_args__ = (
        UniqueConstraint("task_id", "generation", name="uq_developer_session_generation"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_agent_profiles.id", ondelete="SET NULL")
    )
    generation: Mapped[int] = mapped_column(default=1)
    harness: Mapped[str] = mapped_column(String(24))
    harness_version: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(255))
    native_session_id: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(24), default="CREATED")
    workspace_path: Mapped[str] = mapped_column(Text)
    state_path: Mapped[str] = mapped_column(Text)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    requirement_version: Mapped[int] = mapped_column(default=1)
    last_revision: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PricingCatalog(Base):
    __tablename__ = "pricing_catalog"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "model",
            "version",
            "context_tier",
            "service_tier",
            name="uq_pricing_version",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(80))
    context_tier: Mapped[str] = mapped_column(String(40), default="standard")
    service_tier: Mapped[str] = mapped_column(String(40), default="standard")
    input_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    output_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    cached_input_per_million: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    cache_write_per_million: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    source_url: Mapped[str] = mapped_column(Text)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AIRun(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        UniqueConstraint("session_id", "native_turn_id", name="uq_ai_run_native_turn"),
        Index("ix_ai_runs_task_started", "task_id", "started_at"),
        CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="ck_ai_input_tokens"),
        CheckConstraint("output_tokens IS NULL OR output_tokens >= 0", name="ck_ai_output_tokens"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("developer_sessions.id", ondelete="SET NULL")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    native_turn_id: Mapped[str | None] = mapped_column(String(255))
    role_kind: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(255))
    harness: Mapped[str | None] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="RUNNING")
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cache_read_tokens: Mapped[int | None]
    cache_write_tokens: Mapped[int | None]
    reasoning_tokens: Mapped[int | None]
    usage_complete: Mapped[bool] = mapped_column(default=False)
    provider_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    calculated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    reserved_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    pricing_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pricing_catalog.id", ondelete="RESTRICT")
    )
    provider_duration_ms: Mapped[int | None]
    prompt_version: Mapped[str] = mapped_column(String(40))
    raw_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
