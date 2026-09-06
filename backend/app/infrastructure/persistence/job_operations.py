import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import (
    AIAgent,
    HealthState,
    Job,
    JobRole,
    JobState,
    Task,
    TaskAssignment,
    TaskEvent,
    TaskState,
    Team,
    WorkflowDefinition,
    WorkflowNode,
    WorkspaceLease,
)
from app.domain.orchestration import TaskProfiler, resolve_execution_strategy

ROLE_TASK_STATE = {
    JobRole.ORCHESTRATOR: TaskState.NEW,
    JobRole.INTAKE: TaskState.NEW,
    JobRole.THINKER: TaskState.PLANNING,
    JobRole.EXECUTOR: TaskState.IMPLEMENTING,
    JobRole.REVIEWER: TaskState.INTERNAL_REVIEW,
    JobRole.TESTER: TaskState.LOCAL_VALIDATION,
    JobRole.DELIVERER: TaskState.WAITING_GITHUB,
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
    workflow_node: WorkflowNode | None = None,
    workflow_version: int | None = None,
) -> Job:
    if task.execution_profile is None or task.execution_strategy is None:
        profile = TaskProfiler().profile(
            title=task.title,
            description=task.description,
            labels=list(task.labels or []),
        )
        strategy = resolve_execution_strategy(profile)
        task.execution_profile = profile.as_dict()
        task.execution_strategy = strategy.as_dict()
    job_payload = dict(payload or {})
    job_payload.setdefault("execution_strategy", task.execution_strategy)
    job = Job(
        task_id=task.id,
        role=role,
        action=action,
        priority=task.priority if priority is None else priority,
        payload=job_payload,
    )
    session.add(job)
    if workflow_node is None:
        await _pin_job_to_workflow(session, task, job)
    else:
        job.workflow_node_id = workflow_node.id
        job.agent_id = workflow_node.agent_id
        job.team_workflow_version = workflow_version
        task.current_workflow_node_id = workflow_node.id
    task.state = ROLE_TASK_STATE[role]
    await record_event(
        session,
        task.id,
        "JOB_QUEUED",
        {
            "job_id": str(job.id),
            "role": role.value,
            "action": action,
            "workflow_node_id": str(job.workflow_node_id) if job.workflow_node_id else None,
            "workflow_version": job.team_workflow_version,
        },
    )
    return job


async def _pin_job_to_workflow(session: AsyncSession, task: Task, job: Job) -> None:
    """Attach immutable routing identity without changing legacy execution behavior."""
    definition: WorkflowDefinition | None = None
    if task.workflow_id is not None:
        definition = await session.get(WorkflowDefinition, task.workflow_id)
    elif task.team_id is not None:
        definition = await session.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.team_id == task.team_id,
                WorkflowDefinition.is_active.is_(True),
            )
        )
        if definition is not None:
            task.workflow_id = definition.id
            task.workflow_version = definition.version
    if definition is None:
        return
    node = await session.scalar(
        select(WorkflowNode)
        .where(
            WorkflowNode.workflow_id == definition.id,
            WorkflowNode.role == job.role.value,
            WorkflowNode.enabled.is_(True),
        )
        .order_by(WorkflowNode.id)
        .limit(1)
    )
    if node is None:
        return
    job.workflow_node_id = node.id
    job.agent_id = node.agent_id
    job.team_workflow_version = task.workflow_version or definition.version
    task.current_workflow_node_id = node.id


async def claim_next_job(session: AsyncSession, worker_id: str, lease_seconds: int) -> Job | None:
    bind = session.get_bind()
    active_job = aliased(Job)
    active_task = aliased(Task)
    active_team_tasks = (
        select(func.count(func.distinct(active_job.task_id)))
        .join(active_task, active_task.id == active_job.task_id)
        .where(
            active_task.team_id == Task.team_id,
            active_job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
            active_job.task_id != Job.task_id,
        )
        .correlate(Task, Job)
        .scalar_subquery()
    )
    stmt = (
        select(Job)
        .join(Task)
        .outerjoin(Team, Team.id == Task.team_id)
        .outerjoin(AIAgent, AIAgent.id == Job.agent_id)
        .outerjoin(
            HealthState,
            (HealthState.resource_type == "PROVIDER")
            & (HealthState.resource_id == AIAgent.provider),
        )
        .where(
            Job.state.in_([JobState.QUEUED, JobState.RETRY_WAIT]),
            or_(Job.retry_not_before.is_(None), Job.retry_not_before <= datetime.now(UTC)),
            Task.manual_takeover.is_(False),
            Task.state.notin_([TaskState.PAUSED, TaskState.CANCELLED]),
            or_(
                HealthState.id.is_(None),
                HealthState.circuit_state == "CLOSED",
                HealthState.probe_job_id == Job.id,
            ),
            or_(
                Task.team_id.is_(None),
                (
                    Team.enabled.is_(True)
                    & Team.archived_at.is_(None)
                    & (active_team_tasks < Team.max_concurrent_tasks)
                ),
            ),
        )
        .order_by(Job.priority.asc(), Job.created_at.asc())
        .with_for_update(of=Job, skip_locked=True)
        .limit(1)
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    task = await session.get(Task, job.task_id)
    if task is None:
        await session.rollback()
        return None
    if task.team_id is not None and bind.dialect.name == "postgresql":
        # Serialize only claims competing for this Team. The Job row lock alone cannot protect
        # a team-wide concurrency count, while one global advisory key unnecessarily serializes
        # unrelated Teams.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(741963205, hashtext(:team_id))"),
            {"team_id": str(task.team_id)},
        )
        team = await session.get(Team, task.team_id)
        if team is None or not team.enabled or team.archived_at is not None:
            await session.rollback()
            return None
        active_count = await session.scalar(
            select(func.count(func.distinct(Job.task_id)))
            .join(Task, Task.id == Job.task_id)
            .where(
                Task.team_id == task.team_id,
                Job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
                Job.task_id != job.task_id,
            )
        )
        if (active_count or 0) >= team.max_concurrent_tasks:
            await session.rollback()
            return None
    now = datetime.now(UTC)
    job.state = JobState.CLAIMED
    job.worker_id = worker_id
    job.lease_token = uuid.uuid4()
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.retry_not_before = None
    job.finished_at = None
    job.attempt += 1
    job.started_at = now
    await session.execute(
        update(TaskAssignment)
        .where(
            TaskAssignment.task_id == job.task_id,
            TaskAssignment.status == "QUEUED",
        )
        .values(status="RUNNING", started_at=now)
    )
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


async def acquire_workspace_lease(session: AsyncSession, job: Job, lease_seconds: int) -> bool:
    now = datetime.now(UTC)
    lease = await session.get(WorkspaceLease, job.task_id, with_for_update=True)
    if lease and lease.expires_at >= now and lease.job_id != job.id:
        return False
    if lease is None:
        lease = WorkspaceLease(task_id=job.task_id, job_id=job.id)
        session.add(lease)
    lease.job_id = job.id
    lease.token = uuid.uuid4()
    lease.expires_at = now + timedelta(seconds=lease_seconds)
    await session.commit()
    return True


async def release_workspace_lease(session: AsyncSession, job: Job) -> None:
    lease = await session.get(WorkspaceLease, job.task_id, with_for_update=True)
    if lease and lease.job_id == job.id:
        await session.delete(lease)
