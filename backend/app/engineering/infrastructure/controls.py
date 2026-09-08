"""Atomic control operations shared by ticket controls and Team shutdown."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, JobState, ReviewCycle, Task
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.jobs import enqueue_phase
from app.engineering.infrastructure.lifecycle import record_transition


async def control_task(session: AsyncSession, task: Task, action: Action, *, actor: str) -> None:
    await record_transition(
        session, task.id, action, expected_version=task.lifecycle_version, actor=actor
    )
    jobs = await session.scalars(
        select(Job)
        .where(
            Job.task_id == task.id,
            Job.state.in_(
                [
                    JobState.QUEUED,
                    JobState.CLAIMED,
                    JobState.RUNNING,
                    JobState.RETRY_WAIT,
                    JobState.WAITING_HUMAN,
                    JobState.WAITING_PROVIDER,
                    JobState.WAITING_CONFIGURATION,
                    JobState.WAITING_INTEGRATION,
                ]
            ),
        )
        .with_for_update()
    )
    for job in jobs:
        job.state, job.finished_at = JobState.CANCELLED, datetime.now(UTC)
        job.lease_token, job.lease_expires_at = None, None
    await session.flush()
    if action in {Action.RESUME, Action.RELEASE_TAKEOVER}:
        from app.intake.infrastructure.v2_events import apply_pending_feedback

        waiting = await session.scalars(
            select(ReviewCycle).where(
                ReviewCycle.task_id == task.id, ReviewCycle.decision == "CLASSIFY_AFTER_RESUME"
            )
        )
        for row in waiting:
            row.decision = "CLASSIFY_PENDING"
        if await apply_pending_feedback(session, task):
            return
    await enqueue_phase(session, task)  # PAUSED/WAITING_EXTERNAL/CANCELLED do not enqueue.
