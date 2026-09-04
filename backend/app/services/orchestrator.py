import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, JobRole, JobState, Task, TaskEvent, TaskState

ROLE_TASK_STATE = {
    JobRole.INTAKE: TaskState.NEW,
    JobRole.THINKER: TaskState.PLANNING,
    JobRole.EXECUTOR: TaskState.IMPLEMENTING,
    JobRole.REVIEWER: TaskState.INTERNAL_REVIEW,
}


async def record_event(
    session: AsyncSession,
    task_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    source: str = "system",
) -> TaskEvent:
    event = TaskEvent(task_id=task_id, source=source, event_type=event_type, payload=payload)
    session.add(event)
    return event


async def enqueue_job(
    session: AsyncSession,
    task: Task,
    role: JobRole,
    action: str,
    priority: int | None = None,
    payload: dict[str, Any] | None = None,
) -> Job:
    job = Job(
        task_id=task.id,
        role=role,
        action=action,
        priority=task.priority if priority is None else priority,
        payload=payload or {},
    )
    session.add(job)
    task.state = ROLE_TASK_STATE[role]
    await record_event(
        session,
        task.id,
        "JOB_QUEUED",
        {"job_id": str(job.id), "role": role.value, "action": action},
    )
    return job


async def claim_next_job(session: AsyncSession, worker_id: str, lease_seconds: int) -> Job | None:
    # PostgreSQL row locking makes claims safe across scheduler processes.
    stmt = (
        select(Job)
        .join(Task)
        .where(
            Job.state == JobState.QUEUED, Task.state.notin_([TaskState.PAUSED, TaskState.CANCELLED])
        )
        .order_by(Job.priority.asc(), Job.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    now = datetime.now(UTC)
    job.state = JobState.CLAIMED
    job.worker_id = worker_id
    job.lease_token = uuid.uuid4()
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.attempt += 1
    job.started_at = now
    await record_event(
        session, job.task_id, "JOB_CLAIMED", {"job_id": str(job.id), "worker_id": worker_id}
    )
    await session.commit()
    return job


async def recover_expired_jobs(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(Job)
            .where(Job.state.in_([JobState.CLAIMED, JobState.RUNNING]), Job.lease_expires_at < now)
            .values(
                state=JobState.QUEUED,
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                failure_reason="Recovered after expired worker lease",
            )
        ),
    )
    await session.commit()
    return result.rowcount or 0
