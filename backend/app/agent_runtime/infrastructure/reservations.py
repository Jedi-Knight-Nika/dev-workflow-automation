from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.application.develop import DevelopmentBlocked
from app.engineering.infrastructure.task_models import Task
from app.teams.infrastructure.automation import read_policy
from app.teams.infrastructure.team_models import Team


async def budget_usage(
    session: AsyncSession, task: Task, role_kind: str | None = None
) -> tuple[Decimal, Decimal, Decimal]:
    rows = await session.scalars(
        select(AIRun).join(Task, Task.id == AIRun.task_id).where(Task.team_id == task.team_id)
    )
    team_total = task_total = role_total = Decimal(0)
    for prior in rows:
        cost = (
            prior.reserved_cost_usd
            if prior.status == "RUNNING"
            else (
                prior.provider_cost_usd
                if prior.provider_cost_usd is not None
                else prior.calculated_cost_usd
            )
        )
        if cost is None:
            raise DevelopmentBlocked(
                "Unknown native cost must be reconciled before further Team spending"
            )
        team_total += cost
        if prior.task_id == task.id:
            task_total += cost
            if prior.role_kind == role_kind:
                role_total += cost
    return team_total, task_total, role_total


async def development_allowance(session: AsyncSession, task: Task, hard_limit: Decimal) -> Decimal:
    """Plan a turn within remaining Team funds; begin_run still admits it atomically."""
    if task.team_id is None:
        raise DevelopmentBlocked("A Team is required")
    policy = await read_policy(session, task.team_id)
    team_total, task_total, _ = await budget_usage(session, task)
    remaining = min(
        hard_limit - task_total,
        policy.task_budget_usd - task_total,
        policy.team_budget_usd - team_total,
    )
    if remaining <= 0:
        raise DevelopmentBlocked("Team/task spending reservation is exhausted")
    return remaining


async def reserve_budget(
    session: AsyncSession,
    task_id: UUID,
    amount: Decimal,
    *,
    role_kind: str | None = None,
    role_budget: Decimal | None = None,
) -> None:
    """Lock Team before Task; caller inserts the reservation in this transaction."""
    task = await session.get(Task, task_id)
    if task is None or task.team_id is None or not amount.is_finite() or amount <= 0:
        raise DevelopmentBlocked("A positive Team reservation is required")
    team = await session.get(Team, task.team_id, with_for_update=True, populate_existing=True)
    task = await session.get(Task, task_id, with_for_update=True, populate_existing=True)
    if (
        team is None
        or not team.enabled
        or team.execution_paused
        or team.archived_at is not None
        or task is None
        or task.archived_at is not None
        or task.manual_takeover
        or task.team_id != team.id
        or task.status not in {"NEW", "ACTIVE", "WAITING_EXTERNAL"}
    ):
        raise DevelopmentBlocked("Task or Team is suspended; no new spending admitted")
    policy = await read_policy(session, team.id)
    team_total, task_total, role_total = await budget_usage(session, task, role_kind)
    if team_total + amount > policy.team_budget_usd or task_total + amount > policy.task_budget_usd:
        raise DevelopmentBlocked("Team/task spending reservation is exhausted")
    if role_budget is not None and (
        role_kind is None or not role_budget.is_finite() or role_total + amount > role_budget
    ):
        raise DevelopmentBlocked("Task role spending reservation is exhausted")
