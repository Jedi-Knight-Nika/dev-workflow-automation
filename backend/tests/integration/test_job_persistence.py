"""PostgreSQL checks for durable fixed-phase jobs and lease recovery."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engineering.application.jobs import PhaseLease
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.controls import control_task
from app.engineering.infrastructure.jobs import SqlPhaseJobs, enqueue_phase
from app.engineering.infrastructure.task_models import Job, Task
from app.platform.scheduling.states import JobState
from app.teams.infrastructure.team_models import Team

pytestmark = pytest.mark.asyncio


async def test_phase_completion_is_atomic_and_stale_result_cannot_advance(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task_id, team_id = uuid4(), uuid4()
    try:
        async with postgres_session_factory.begin() as session:
            session.add(Team(id=team_id, name=f"jobs-{team_id}"))
            await session.flush()
            task = Task(
                id=task_id,
                team_id=team_id,
                title="Execution unit",
                status="NEW",
                stage="INTAKE",
                wait_reason="NONE",
            )
            session.add(task)
            await session.flush()
            first = await enqueue_phase(session, task)
            duplicate = await enqueue_phase(session, task)
            assert first is duplicate
        store = SqlPhaseJobs(postgres_session_factory, "test", 30)
        lease = await store.claim()
        assert lease is not None and lease.task_id == task_id
        await store.complete(lease, Action.START)
        await store.complete(lease, Action.START)  # Redelivery is harmless.
        async with postgres_session_factory() as session:
            task = await session.get(Task, task_id)
            assert task and task.stage == "DEVELOPING" and task.lifecycle_version == 2
            jobs = list(await session.scalars(select(Job).where(Job.task_id == task_id)))
            assert len(jobs) == 2
            assert {j.action for j in jobs} == {"INTERPRET_EVENT", "DEVELOPER_TURN"}
            assert len([j for j in jobs if j.state == JobState.QUEUED]) == 1
        lease = await store.claim()
        assert lease is not None
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id, with_for_update=True)
            assert task is not None
            await control_task(session, task, Action.PAUSE, actor="operator")
        assert not await store.heartbeat(lease)
        await store.complete(lease, Action.IMPLEMENTED)
        async with postgres_session_factory() as session:
            task = await session.get(Task, task_id)
            assert task and task.status == "PAUSED" and task.stage == "DEVELOPING"
    finally:
        async with postgres_session_factory.begin() as session:
            await session.execute(delete(Task).where(Task.id == task_id))
            await session.execute(delete(Team).where(Team.id == team_id))


async def test_expired_lease_blocks_without_replaying_paid_work(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task_id, team_id = uuid4(), uuid4()
    try:
        async with postgres_session_factory.begin() as session:
            session.add(Team(id=team_id, name=f"recovery-{team_id}"))
            await session.flush()
            task = Task(
                id=task_id,
                team_id=team_id,
                title="Execution recovery",
                status="NEW",
                stage="INTAKE",
                wait_reason="NONE",
            )
            session.add(task)
            await session.flush()
            job = await enqueue_phase(session, task)
            assert job is not None
            job_id = job.id
        store = SqlPhaseJobs(postgres_session_factory, "test", 30)
        lease = await store.claim()
        assert isinstance(lease, PhaseLease)
        async with postgres_session_factory.begin() as session:
            job = await session.get(Job, job_id)
            assert job is not None
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await store.recover()
        async with postgres_session_factory() as session:
            task, job = await session.get(Task, task_id), await session.get(Job, job_id)
            assert task and task.status == "WAITING_HUMAN"
            assert job and job.state == JobState.WAITING_HUMAN and job.lease_token is None
        assert await store.claim() is None
    finally:
        async with postgres_session_factory.begin() as session:
            await session.execute(delete(Task).where(Task.id == task_id))
            await session.execute(delete(Team).where(Team.id == team_id))
