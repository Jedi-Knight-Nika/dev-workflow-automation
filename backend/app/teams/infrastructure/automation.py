from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.persistence.base import Base
from app.teams.domain.automation import AutomationPolicy


class TeamAutomationPolicy(Base):
    __tablename__ = "team_automation_policies"
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(default=1)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


def policy_payload(policy: AutomationPolicy) -> dict[str, Any]:
    result = asdict(policy)
    result["repository_ids"] = [str(value) for value in policy.repository_ids]
    result["task_budget_usd"] = str(policy.task_budget_usd)
    result["team_budget_usd"] = str(policy.team_budget_usd)
    return result


async def read_policy(
    session: AsyncSession, team_id: UUID, *, lock: bool = False
) -> AutomationPolicy:
    from decimal import Decimal

    row = await session.get(TeamAutomationPolicy, team_id, with_for_update=lock)
    if row is None:
        return AutomationPolicy()
    data = dict(row.configuration)
    data["repository_ids"] = tuple(UUID(value) for value in data.get("repository_ids", []))
    data["task_budget_usd"] = Decimal(data["task_budget_usd"])
    data["team_budget_usd"] = Decimal(data["team_budget_usd"])
    return AutomationPolicy(**data)
