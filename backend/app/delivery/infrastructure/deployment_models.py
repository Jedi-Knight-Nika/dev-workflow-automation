from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class DeploymentObservation(Base):
    __tablename__ = "deployment_observations"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "deployment_id", "observation_id", name="uq_deployment_observation"
        ),
        Index("ix_deployment_repository_time", "repository_id", "occurred_at", "id"),
        Index("ix_deployment_time", "occurred_at", "id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    deployment_id: Mapped[str] = mapped_column(String(30))
    observation_id: Mapped[str] = mapped_column(String(30))
    sha: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(255))
    production: Mapped[bool | None]
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
