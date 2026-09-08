from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Repository, Task, TaskEvent, Team
from app.intake.infrastructure.v2_events import github_event


async def recheck_review(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Recover missed CI/review webhooks without calling an AI model.

    At most one due task per scheduler pass, once per five minutes per task.
    Paused/disabled Teams are excluded; API failures retain a bounded audit entry.
    """
    now = datetime.now(UTC)
    async with sessions.begin() as session:
        task = await session.scalar(
            select(Task)
            .join(Team)
            .where(
                Task.execution_version == 2,
                Task.status == "WAITING_EXTERNAL",
                Task.stage == "REVIEWING",
                Task.manual_takeover.is_(False),
                Task.archived_at.is_(None),
                Task.updated_at < now - timedelta(minutes=5),
                Team.enabled.is_(True),
                Team.archived_at.is_(None),
            )
            .order_by(Task.updated_at)
            .with_for_update(of=Task, skip_locked=True)
            .limit(1)
        )
        if task is None:
            return False
        task.updated_at = now
        repo = await session.get(Repository, task.repository_id) if task.repository_id else None
        if repo is None:
            return False
        try:
            async with session.begin_nested():
                await github_event(session, task, repo, "periodic_recheck", {"at": now.isoformat()})
        except Exception as exc:  # noqa: BLE001 - preserve the wait, never an inference retry
            session.add(
                TaskEvent(
                    task_id=task.id,
                    source="github",
                    event_type="V2_RECHECK_UNAVAILABLE",
                    payload={"failure_code": type(exc).__name__},
                )
            )
    return True
