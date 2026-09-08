"""Additive durable identities and summaries; never raw Prometheus samples."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class RunnerResourceBinding(Base):
    __tablename__ = "runner_resource_bindings"
    __table_args__ = (Index("ix_resource_task_started", "task_id", "started_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    runner_run_id: Mapped[UUID] = mapped_column(unique=True)
    container_id: Mapped[str] = mapped_column(String(64), unique=True)
    container_name: Mapped[str] = mapped_column(String(255))
    service_kind: Mapped[str] = mapped_column(String(24))
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    agent_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("team_agent_profiles.id", ondelete="SET NULL")
    )
    role: Mapped[str | None] = mapped_column(String(24))
    phase: Mapped[str | None] = mapped_column(String(24))
    host_id: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None]
    oom_killed: Mapped[bool | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunnerResourceSummary(Base):
    __tablename__ = "runner_resource_summaries"
    runner_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runner_resource_bindings.runner_run_id", ondelete="CASCADE"), primary_key=True
    )
    sample_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sample_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sample_coverage_ratio: Mapped[float | None]
    metrics_complete: Mapped[bool] = mapped_column(default=False)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InfrastructureEvent(Base):
    __tablename__ = "infrastructure_events"
    __table_args__ = (Index("ix_infrastructure_occurred", "occurred_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    host_id: Mapped[str] = mapped_column(String(80))
    container_id: Mapped[str] = mapped_column(String(64))
    service_name: Mapped[str] = mapped_column(String(80))
    runner_run_id: Mapped[UUID | None]
    event_type: Mapped[str] = mapped_column(String(40))
    exit_code: Mapped[int | None]
    oom_killed: Mapped[bool | None]


class ServiceIncident(Base):
    __tablename__ = "service_incidents"
    __table_args__ = (Index("ix_incident_opened", "opened_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dedup_key: Mapped[str] = mapped_column(String(180), unique=True)
    service_key: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(16))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(24), default="docker")
    summary: Mapped[str] = mapped_column(String(255))


class MonitoringConfiguration(Base):
    __tablename__ = "monitoring_configuration"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default="default")
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ContainerObservation(Base):
    __tablename__ = "container_observations"
    container_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    host_id: Mapped[str] = mapped_column(String(80))
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
