"""Transactional phase claiming. No model-role routing or provider calls."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.platform.scheduling.states import JobState
from app.teams.infrastructure.team_models import Team

# Team concurrency limits paid/agent execution slots. Deterministic lifecycle
# handoffs must not wait behind another Developer: validation, publication and
# merge are safe to run while another task is coding.
CONCURRENCY_SLOT_ACTIONS = ("INTERPRET_EVENT", "THINKER_TURN", "DEVELOPER_TURN")


async def record_event(
    session: AsyncSession,
    task_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    *,
    source: str = "system",
) -> None:
    session.add(TaskEvent(task_id=task_id, event_type=event_type, payload=payload, source=source))


async def request_execution(session: AsyncSession, task: Task, *, actor: str) -> None:
    """Register a new task or record an actionable, free configuration wait."""
    from app.engineering.domain.lifecycle import Action, WaitReason
    from app.engineering.infrastructure.enrollment import enroll
    from app.engineering.infrastructure.lifecycle import record_transition
    from app.platform.configuration.settings import get_settings

    try:
        async with session.begin_nested():
            await enroll(session, task, get_settings(), actor=actor)
    except ValueError as exc:
        await session.refresh(task)
        if task.status in {"NEW", "ACTIVE", "WAITING_HUMAN"}:
            await record_transition(
                session,
                task.id,
                Action.BLOCK,
                expected_version=task.lifecycle_version,
                actor=actor,
                wait_reason=WaitReason.MISSING_CONFIGURATION,
            )
        await record_event(
            session,
            task.id,
            "TASK_CONFIGURATION_REQUIRED",
            {"reason": str(exc)[:1000], "actor": actor},
            source=actor,
        )


async def claim_next_job(
    session: AsyncSession,
    worker_id: str,
    lease_seconds: int,
) -> Job | None:
    now = datetime.now(UTC)
    candidate = aliased(Job)
    already_running = (
        select(candidate.id)
        .where(
            candidate.task_id == Job.task_id,
            candidate.id != Job.id,
            candidate.state.in_([JobState.CLAIMED, JobState.RUNNING]),
        )
        .correlate(Job)
        .exists()
    )
    busy_job, busy_task = aliased(Job), aliased(Task)
    occupied = (
        select(func.count(func.distinct(busy_job.task_id)))
        .join(busy_task, busy_task.id == busy_job.task_id)
        .where(
            busy_task.team_id == Team.id,
            busy_job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
            busy_job.action.in_(CONCURRENCY_SLOT_ACTIONS),
        )
        .correlate(Team)
        .scalar_subquery()
    )
    job = await session.scalar(
        select(Job)
        .join(Task)
        .join(Team, Team.id == Task.team_id)
        .where(
            Job.state.in_([JobState.QUEUED, JobState.RETRY_WAIT]),
            or_(Job.retry_not_before.is_(None), Job.retry_not_before <= now),
            Task.status.in_(["NEW", "ACTIVE"]),
            Task.manual_takeover.is_(False),
            Task.archived_at.is_(None),
            Team.enabled.is_(True),
            Team.execution_paused.is_(False),
            Team.archived_at.is_(None),
            occupied < Team.max_concurrent_tasks,
            ~already_running,
        )
        .order_by(Job.priority, Job.created_at)
        .with_for_update(of=Job, skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    task = await session.get(Task, job.task_id)
    if task is None or task.team_id is None:
        await session.rollback()
        return None
    if session.get_bind().dialect.name == "postgresql":
        # Recheck capacity after taking a Team-scoped lock: different Teams stay parallel.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(741963205, hashtext(:team_id))"),
            {"team_id": str(task.team_id)},
        )
    team = await session.get(Team, task.team_id, populate_existing=True)
    active = await session.scalar(
        select(func.count(func.distinct(Job.task_id)))
        .join(Task)
        .where(
            Task.team_id == task.team_id,
            Job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
            Job.action.in_(CONCURRENCY_SLOT_ACTIONS),
        )
    )
    if (
        team is None
        or not team.enabled
        or team.execution_paused
        or team.archived_at
        or (active or 0) >= team.max_concurrent_tasks
    ):
        await session.rollback()
        return None
    job.state = JobState.CLAIMED
    job.worker_id, job.lease_token = worker_id, uuid.uuid4()
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.retry_not_before = job.finished_at = None
    job.attempt += 1
    job.started_at = now
    await record_event(
        session, job.task_id, "JOB_CLAIMED", {"job_id": str(job.id), "worker_id": worker_id}
    )
    await session.commit()
    return job
