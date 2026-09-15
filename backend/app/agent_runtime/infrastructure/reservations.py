from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.cost_queries import (
    budget_cost,
    engineering_cost,
    settled_cost,
    unsettled_engineering_usage,
    unsettled_usage,
)
from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.application.develop import DevelopmentBlocked
from app.engineering.infrastructure.task_models import Task
from app.platform.configuration.settings import get_settings
from app.teams.infrastructure.automation import read_policy
from app.teams.infrastructure.team_models import Team


async def consumed_cost(
    session: AsyncSession, task_id: UUID, *, include_coordinator_reservations: bool = False
) -> Decimal | None:
    """Known cost; Developer admission may include an in-flight Coordinator reservation."""
    cost = engineering_cost() if include_coordinator_reservations else settled_cost()
    pending = (
        unsettled_engineering_usage() if include_coordinator_reservations else unsettled_usage()
    )
    total, unsettled = (
        await session.execute(
            select(
                func.sum(cost),
                func.max(case((pending, 1), else_=0)),
            ).where(AIRun.task_id == task_id)
        )
    ).one()
    if unsettled:
        return None
    return total if total is not None else Decimal(0)


async def budget_usage(
    session: AsyncSession, task: Task, role_kind: str | None = None
) -> tuple[Decimal, Decimal, Decimal]:
    cost = budget_cost()
    is_task = AIRun.task_id == task.id
    team_total, task_total, role_total, has_unknown_cost = (
        await session.execute(
            select(
                func.sum(cost),
                func.sum(case((is_task, cost), else_=0)),
                func.sum(case((and_(is_task, AIRun.role_kind == role_kind), cost), else_=0)),
                func.max(case((cost.is_(None), 1), else_=0)),
            )
            .join(Task, Task.id == AIRun.task_id)
            .where(Task.team_id == task.team_id)
        )
    ).one()
    if has_unknown_cost:
        raise DevelopmentBlocked(
            "Unknown native cost must be reconciled before further Team spending"
        )
    return (
        team_total if team_total is not None else Decimal(0),
        task_total if task_total is not None else Decimal(0),
        role_total if role_total is not None else Decimal(0),
    )


async def development_allowance(
    session: AsyncSession,
    task: Task,
    hard_limit: Decimal,
    minimum_turn_allowance: Decimal = Decimal("0.05"),
) -> Decimal:
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
    if remaining < minimum_turn_allowance:
        raise DevelopmentBlocked(
            "Remaining Team/task budget is below the minimum safe Developer turn allowance"
        )
    return remaining


async def reserve_budget(
    session: AsyncSession,
    task_id: UUID,
    amount: Decimal,
    *,
    role_kind: str | None = None,
    role_budget: Decimal | None = None,
    allow_coordination: bool = False,
) -> None:
    """Lock Team before Task; caller inserts the reservation in this transaction."""
    task = await session.get(Task, task_id)
    if task is None or task.team_id is None or not amount.is_finite() or amount <= 0:
        raise DevelopmentBlocked("A positive Team reservation is required")
    account_limit = get_settings().account_monthly_budget_usd
    if account_limit is not None and session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(741963207)"))
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
        or (
            task.status not in {"NEW", "ACTIVE", "WAITING_EXTERNAL"}
            and not (allow_coordination and role_kind == "COORDINATOR")
        )
    ):
        raise DevelopmentBlocked("Task or Team is suspended; no new spending admitted")
    policy = await read_policy(session, team.id)
    month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if account_limit is not None:
        account_total, unknown = await periodic_usage(session, month)
        if unknown or account_total + amount > account_limit:
            raise DevelopmentBlocked("Account monthly budget is exhausted or usage is unknown")
    if policy.monthly_budget_usd is not None:
        monthly_total, unknown = await periodic_usage(session, month, team.id)
        if unknown or monthly_total + amount > policy.monthly_budget_usd:
            raise DevelopmentBlocked("Team monthly spending reservation is exhausted")
    team_total, task_total, role_total = await budget_usage(session, task, role_kind)
    if team_total + amount > policy.team_budget_usd or task_total + amount > policy.task_budget_usd:
        raise DevelopmentBlocked("Team/task spending reservation is exhausted")
    if role_budget is not None and (
        role_kind is None or not role_budget.is_finite() or role_total + amount > role_budget
    ):
        raise DevelopmentBlocked("Task role spending reservation is exhausted")


async def periodic_usage(
    session: AsyncSession, since: datetime, team_id: UUID | None = None
) -> tuple[Decimal, bool]:
    """UTC purchase period plus unresolved reservations from previous periods."""
    cost = budget_cost()
    query = (
        select(func.sum(cost), func.max(case((cost.is_(None), 1), else_=0)))
        .join(Task, Task.id == AIRun.task_id)
        .where(or_(AIRun.started_at >= since, AIRun.status == "RUNNING", cost.is_(None)))
    )
    if team_id is not None:
        query = query.where(Task.team_id == team_id)
    amount, unknown = (await session.execute(query)).one()
    return amount or Decimal(0), bool(unknown)
