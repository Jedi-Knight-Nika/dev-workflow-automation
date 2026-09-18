"""Persist observed plan changes with their run receipt; no rendering dependency."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.domain.work_history import public_work_plans
from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.infrastructure.task_models import TaskEvent


def record_work_history(session: AsyncSession, run: AIRun, snapshot: dict[str, Any]) -> None:
    plans = public_work_plans(snapshot.get("work_plans"))
    prior = run.token_efficiency if isinstance(run.token_efficiency, dict) else {}
    previous = public_work_plans(prior.get("work_plans"))
    if plans and plans != previous:
        session.add(
            TaskEvent(
                task_id=run.task_id,
                source="developer",
                event_type="WORK_PLAN_UPDATED",
                payload={
                    "run_id": str(run.id),
                    "job_id": str(run.job_id) if run.job_id else None,
                    "work_plans": plans,
                },
            )
        )
