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


class AgentConfig(Base):
    __tablename__ = "agent_configs"
    role: Mapped[JobRole] = mapped_column(Enum(JobRole), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    provider: Mapped[str] = mapped_column(String(50), default="openai")
    model: Mapped[str] = mapped_column(String(255), default="")
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AgentKnowledgeSource(Base):
    __tablename__ = "agent_knowledge_sources"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role: Mapped[JobRole] = mapped_column(Enum(JobRole))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentKnowledgeChunk(Base):
    __tablename__ = "agent_knowledge_chunks"
    __table_args__ = (Index("ix_agent_knowledge_chunks_role", "role"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_knowledge_sources.id", ondelete="CASCADE")
    )
    role: Mapped[JobRole] = mapped_column(Enum(JobRole))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[str] = mapped_column(Text)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    category: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text, default="")
    system_instructions: Mapped[str] = mapped_column(Text, default="")
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_results: Mapped[list[str]] = mapped_column(JSON, default=list)
    knowledge_collection_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_provider: Mapped[str | None] = mapped_column(String(50))
    default_model: Mapped[str | None] = mapped_column(String(255))
    default_reasoning_effort: Mapped[str] = mapped_column(String(20), default="default")
    default_timeout_minutes: Mapped[int] = mapped_column(Integer, default=30)
    default_max_retries: Mapped[int] = mapped_column(Integer, default=2)
    enabled: Mapped[bool] = mapped_column(default=True)
    built_in: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIAgent(Base):
    __tablename__ = "ai_agents"
    __table_args__ = (UniqueConstraint("team_id", "name", name="uq_ai_agent_team_name"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(255))
    custom_instructions: Mapped[str] = mapped_column(Text, default="")
    permission_overrides: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    knowledge_collection_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
