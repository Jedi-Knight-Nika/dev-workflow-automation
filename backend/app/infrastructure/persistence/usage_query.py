"""One read model for legacy calls and native turns; costs are never fabricated."""

from typing import Any

from sqlalchemy import String, case, cast, func, select, union_all
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.db.models import AIRun, Job, Task, WorkerRun


def metered_runs() -> Subquery:
    return union_all(
        select(
            WorkerRun.job_id.label("job_id"),
            Job.task_id.label("task_id"),
            Task.team_id.label("team_id"),
            cast(WorkerRun.role, String).label("role"),
            WorkerRun.provider.label("provider"),
            WorkerRun.input_tokens.label("input_tokens"),
            WorkerRun.output_tokens.label("output_tokens"),
            WorkerRun.estimated_cost_usd.label("cost_usd"),
            WorkerRun.created_at.label("started_at"),
            WorkerRun.duration_ms.label("duration_ms"),
        )
        .join(Job, Job.id == WorkerRun.job_id)
        .join(Task, Task.id == Job.task_id),
        select(
            AIRun.job_id,
            AIRun.task_id,
            Task.team_id,
            AIRun.role_kind,
            AIRun.provider,
            AIRun.input_tokens,
            AIRun.output_tokens,
            func.coalesce(AIRun.provider_cost_usd, AIRun.calculated_cost_usd),
            AIRun.started_at,
            AIRun.provider_duration_ms,
        ).join(Task, Task.id == AIRun.task_id),
    ).subquery("metered_runs")


def complete_cost(column: ColumnElement[Any]) -> ColumnElement[Any]:
    # SQL SUM normally hides missing measurements. One unknown makes the total unknown.
    return case((func.count() == func.count(column), func.sum(column)), else_=None)
