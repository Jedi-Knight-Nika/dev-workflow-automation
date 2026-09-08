import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base, utcnow


class TeamAgentProfile(Base):
    __tablename__ = "team_agent_profiles"
    __table_args__ = (
        UniqueConstraint("team_id", "role_kind", name="uq_team_agent_profile_role"),
        CheckConstraint(
            "role_kind IN ('INTERPRETER','DEVELOPER','THINKER','REVIEWER')", name="ck_profile_role"
        ),
        CheckConstraint(
            "hard_budget_usd IS NULL OR hard_budget_usd > 0", name="ck_profile_hard_budget"
        ),
        CheckConstraint(
            "soft_budget_usd IS NULL OR soft_budget_usd > 0", name="ck_profile_soft_budget"
        ),
        CheckConstraint(
            "soft_budget_usd IS NULL OR hard_budget_usd IS NULL OR soft_budget_usd <= hard_budget_usd",
            name="ck_profile_budget_order",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    role_kind: Mapped[str] = mapped_column(String(24))
    display_name: Mapped[str] = mapped_column(String(120))
    avatar: Mapped[str] = mapped_column(String(500), default="")
    enabled: Mapped[bool] = mapped_column(default=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(255))
    harness: Mapped[str | None] = mapped_column(String(24))
    effort: Mapped[str] = mapped_column(String(20), default="medium")
    supplemental_instructions: Mapped[str] = mapped_column(Text, default="")
    prompt_version: Mapped[str] = mapped_column(String(40), default="v2.1")
    soft_budget_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    hard_budget_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
