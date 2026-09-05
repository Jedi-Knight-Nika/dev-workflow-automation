import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Task, TaskAssignment, Team

DEFAULT_TEAM_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def assign_routed_team(
    session: AsyncSession, task: Task, *, reason: str
) -> TaskAssignment | None:
    teams = list(
        (
            await session.scalars(
                select(Team)
                .where(Team.enabled.is_(True), Team.archived_at.is_(None))
                .order_by(Team.created_at)
            )
        ).all()
    )
    eligible = [
        team
        for team in teams
        if not team.repository_ids
        or task.repository_id is None
        or str(task.repository_id) in team.repository_ids
    ]
    if not eligible:
        return None
    queue_counts = {
        team_id: count
        for team_id, count in (
            await session.execute(
                select(TaskAssignment.team_id, func.count())
                .where(TaskAssignment.status.in_(["QUEUED", "RUNNING"]))
                .group_by(TaskAssignment.team_id)
            )
        ).all()
    }
    team = min(
        eligible,
        key=lambda candidate: (
            queue_counts.get(candidate.id, 0) / candidate.max_concurrent_tasks,
            candidate.id != DEFAULT_TEAM_ID,
        ),
    )
    position = (
        int(
            await session.scalar(
                select(func.coalesce(func.max(TaskAssignment.queue_position), 0)).where(
                    TaskAssignment.team_id == team.id
                )
            )
            or 0
        )
        + 1
    )
    task.team_id = team.id
    assignment = TaskAssignment(
        task_id=task.id,
        team_id=team.id,
        queue_position=position,
        reason=reason,
    )
    session.add(assignment)
    return assignment
