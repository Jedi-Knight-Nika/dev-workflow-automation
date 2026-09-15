"""Bounded historical policy and execution evidence for preflight and live snapshots."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.activity.application.ports import ActivityWindow
from app.activity.infrastructure.models import ActivityEvent
from app.engineering.infrastructure.job_queue import CONCURRENCY_SLOT_ACTIONS
from app.engineering.infrastructure.task_models import Task
from app.teams.infrastructure.team_models import Team, TeamCapacityChange


async def capacity_evidence(
    session: AsyncSession, window: ActivityWindow, team_ids: list[UUID], through: int, limit: int
) -> dict[str, Any]:
    if not team_ids:
        return {
            "teams": [],
            "truncated": False,
            "as_of": min(window.end, datetime.now(UTC)),
            "through_sequence": through,
        }
    teams = (await session.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids)))).all()
    prior = list(
        await session.scalars(
            select(TeamCapacityChange)
            .where(
                TeamCapacityChange.team_id.in_(team_ids),
                TeamCapacityChange.created_at < window.start,
            )
            .distinct(TeamCapacityChange.team_id)
            .order_by(
                TeamCapacityChange.team_id,
                TeamCapacityChange.created_at.desc(),
                TeamCapacityChange.id.desc(),
            )
        )
    )
    changes = list(
        await session.scalars(
            select(TeamCapacityChange)
            .where(
                TeamCapacityChange.team_id.in_(team_ids),
                TeamCapacityChange.created_at >= window.start,
                TeamCapacityChange.created_at <= window.end,
            )
            .order_by(TeamCapacityChange.created_at, TeamCapacityChange.id)
            .limit(limit + 1)
        )
    )
    finished = aliased(ActivityEvent)
    rows = (
        await session.execute(
            select(ActivityEvent, Task.team_id, finished.occurred_at)
            .select_from(ActivityEvent)
            .join(Task, Task.id == ActivityEvent.task_id)
            .outerjoin(
                finished,
                (finished.source_type == "job")
                & (finished.source_id == ActivityEvent.payload["job_id"].astext + ":finished")
                & (finished.sequence <= through),
            )
            .where(
                ActivityEvent.source_type == "job",
                ActivityEvent.kind == "JOB_STARTED",
                or_(
                    ActivityEvent.payload["action"].astext.in_(CONCURRENCY_SLOT_ACTIONS),
                    ActivityEvent.payload["action"].astext.is_(None),
                ),
                Task.team_id.in_(team_ids),
                ActivityEvent.sequence <= through,
                ActivityEvent.occurred_at <= window.end,
                or_(finished.occurred_at.is_(None), finished.occurred_at >= window.start),
            )
            .order_by(ActivityEvent.occurred_at, ActivityEvent.sequence)
            .limit(limit + 1)
        )
    ).all()
    grouped: dict[UUID, dict[str, Any]] = {
        id: {"id": str(id), "name": name, "limits": [], "jobs": []} for id, name in teams
    }
    for change in prior + changes[:limit]:
        if team := grouped.get(change.team_id):
            team["limits"].append({"at": change.created_at, "capacity": change.capacity})
    for event, team_id, end in rows[:limit]:
        if team := grouped.get(team_id):
            team["jobs"].append(
                {
                    "id": str(event.payload.get("job_id")),
                    "task_id": str(event.task_id),
                    "start": event.occurred_at,
                    "end": end,
                    "complete": event.payload.get("attempt") == 1
                    and event.payload.get("action") in CONCURRENCY_SLOT_ACTIONS,
                }
            )
    return {
        "as_of": min(window.end, datetime.now(UTC)),
        "through_sequence": through,
        "truncated": len(changes) > limit or len(rows) > limit,
        "teams": list(grouped.values()),
    }
