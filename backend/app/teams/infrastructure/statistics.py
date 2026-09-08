from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIRun, LocalModelRun, Task, TaskPhaseRun
from app.infrastructure.persistence.usage_query import complete_cost


async def statistics(session: AsyncSession, team_id: UUID | None, days: int = 30) -> dict[str, Any]:
    start = datetime.now(UTC) - timedelta(days=days)
    scope = [Task.team_id == team_id] if team_id else []
    runs = (
        await session.execute(
            select(
                AIRun.role_kind,
                AIRun.provider,
                AIRun.model,
                func.count(AIRun.id),
                func.sum(AIRun.input_tokens),
                func.sum(AIRun.output_tokens),
                complete_cost(func.coalesce(AIRun.provider_cost_usd, AIRun.calculated_cost_usd)),
                func.count(AIRun.id).filter(AIRun.usage_complete.is_(False)),
                func.sum(AIRun.provider_duration_ms),
                func.count(AIRun.id).filter(AIRun.prompt_version == "v2.compaction.1"),
            )
            .join(Task, Task.id == AIRun.task_id)
            .where(AIRun.started_at >= start, *scope)
            .group_by(AIRun.role_kind, AIRun.provider, AIRun.model)
        )
    ).all()
    phases = (
        await session.execute(
            select(
                TaskPhaseRun.stage,
                TaskPhaseRun.status,
                func.count(TaskPhaseRun.id),
                func.sum(func.extract("epoch", TaskPhaseRun.finished_at - TaskPhaseRun.started_at)),
            )
            .join(Task, Task.id == TaskPhaseRun.task_id)
            .where(TaskPhaseRun.started_at >= start, *scope)
            .group_by(TaskPhaseRun.stage, TaskPhaseRun.status)
        )
    ).all()
    local = (
        await session.execute(
            select(
                LocalModelRun.model,
                func.count(LocalModelRun.id),
                func.sum(LocalModelRun.duration_ms),
                func.count(LocalModelRun.id).filter(LocalModelRun.status == "FAILED"),
            )
            .join(Task, Task.id == LocalModelRun.task_id)
            .where(LocalModelRun.started_at >= start, *scope)
            .group_by(LocalModelRun.model)
        )
    ).all()
    return {
        "scope": "v2-only",
        "team_id": str(team_id) if team_id else None,
        "from": start.isoformat(),
        "days": days,
        "cloud_runs": [
            {
                "role": role,
                "provider": provider,
                "model": model,
                "attempts": count,
                "input_tokens": inputs,
                "output_tokens": outputs,
                "cost_usd": str(cost) if cost is not None else None,
                "incomplete_usage_runs": incomplete,
                "provider_time_ms": duration,
                "compactions": compactions,
            }
            for role, provider, model, count, inputs, outputs, cost, incomplete, duration, compactions in runs
        ],
        "phases": [
            {
                "stage": stage,
                "status": status,
                "count": count,
                "finished_duration_seconds": float(seconds) if seconds is not None else None,
            }
            for stage, status, count, seconds in phases
        ],
        "local_runs": [
            {"model": model, "attempts": count, "duration_ms": duration, "failed": failed}
            for model, count, duration, failed in local
        ],
    }
