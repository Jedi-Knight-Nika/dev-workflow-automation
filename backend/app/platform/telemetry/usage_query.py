"""One read model for metered AI runs; costs are never fabricated."""

from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.infrastructure.task_models import Task


def metered_runs() -> Subquery:
    return (
        select(
            AIRun.job_id,
            AIRun.task_id,
            Task.team_id,
            AIRun.role_kind.label("role"),
            AIRun.provider,
            AIRun.input_tokens,
            AIRun.output_tokens,
            func.coalesce(AIRun.provider_cost_usd, AIRun.calculated_cost_usd).label("cost_usd"),
            AIRun.started_at,
            AIRun.provider_duration_ms.label("duration_ms"),
        ).join(Task, Task.id == AIRun.task_id)
    ).subquery("metered_runs")


def complete_cost(column: ColumnElement[Any]) -> ColumnElement[Any]:
    # SQL SUM normally hides missing measurements. One unknown makes the total unknown.
    return case((func.count() == func.count(column), func.sum(column)), else_=None)
