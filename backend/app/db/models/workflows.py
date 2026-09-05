from __future__ import annotations

# Model modules intentionally share this compact SQLAlchemy import vocabulary.
# ruff: noqa: F401
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.operational_states import IndexStatus, IntegrationStatus, JobRole, JobState
from app.domain.tasks import TaskState

from ._base import utcnow


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), unique=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(120), default="Team workflow")
    is_active: Mapped[bool] = mapped_column(default=True)
    entry_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WorkflowRevision(Base):
    """Immutable graph snapshot used to explain historical routing decisions."""

    __tablename__ = "workflow_revisions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "version", name="uq_workflow_revision_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE")
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_agents.id", ondelete="SET NULL")
    )
    role: Mapped[str] = mapped_column(String(30))
    node_type: Mapped[str] = mapped_column(String(30), default="AGENT")
    system_node_type: Mapped[str | None] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(100))
    position_x: Mapped[float] = mapped_column(Numeric(12, 3))
    position_y: Mapped[float] = mapped_column(Numeric(12, 3))
    enabled: Mapped[bool] = mapped_column(default=True)
    activation_policy: Mapped[str] = mapped_column(String(20), default="any")
    batch_window_seconds: Mapped[int] = mapped_column(Integer, default=0)
    integration_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    repository_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    provider: Mapped[str] = mapped_column(String(50), default="openai")
    model: Mapped[str] = mapped_column(String(255), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    model_validation_status: Mapped[str] = mapped_column(String(30), default="NOT_CONFIGURED")
    model_validation_message: Mapped[str | None] = mapped_column(Text)
    model_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    integration_mode: Mapped[str] = mapped_column(String(20), default="webhook")
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    filter_assignee_id: Mapped[str] = mapped_column(String(255), default="")
    filter_state_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    integration_sync_status: Mapped[str] = mapped_column(String(30), default="IDLE")
    integration_sync_error: Mapped[str | None] = mapped_column(Text)
    integration_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reasoning_effort: Mapped[str] = mapped_column(String(20), default="default")
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    temperature: Mapped[float | None] = mapped_column(Numeric(4, 2))
    timeout_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    max_review_cycles: Mapped[int] = mapped_column(Integer, default=3)
    context_depth: Mapped[str] = mapped_column(String(20), default="normal")
    rag_retrieval_depth: Mapped[str] = mapped_column(String(20), default="normal")
    fallback_provider: Mapped[str | None] = mapped_column(String(50))
    fallback_model: Mapped[str | None] = mapped_column(String(255))


class WorkflowEdge(Base):
    __tablename__ = "workflow_edges"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "source_node_id",
            "target_node_id",
            "outcome",
            name="uq_workflow_edge_route",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE")
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_nodes.id", ondelete="CASCADE")
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_nodes.id", ondelete="CASCADE")
    )
    outcome: Mapped[str] = mapped_column(String(30), default="success")
    required: Mapped[bool] = mapped_column(default=True)
    job_type: Mapped[str | None] = mapped_column(String(100))
    internal_task_state: Mapped[str | None] = mapped_column(String(50))
    external_status_key: Mapped[str | None] = mapped_column(String(100))
    priority_override: Mapped[int | None] = mapped_column(Integer)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class WorkflowTransition(Base):
    __tablename__ = "workflow_transitions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE")
    )
    workflow_version: Mapped[int] = mapped_column(Integer)
    from_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    result_type: Mapped[str] = mapped_column(String(80))
    matched_edge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    to_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    new_job_type: Mapped[str | None] = mapped_column(String(100))
    internal_state: Mapped[str | None] = mapped_column(String(50))
    external_status_key: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
