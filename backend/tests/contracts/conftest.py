"""PostgreSQL harnesses. Other adapters provide the same hooks without changing contract tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import delete, select

from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.controls import control_task
from app.engineering.infrastructure.jobs import SqlPhaseJobs, enqueue_phase
from app.platform.messaging.infrastructure.outbox import SqlEventOutbox
from app.platform.persistence.registry import Job, NotificationOutbox, Task, Team
from app.platform.scheduling.states import JobState
from tests.contracts.support import PhaseSnapshot
from tests.integration.conftest import postgres_session_factory

__all__ = ["postgres_session_factory"]


class PostgresPhaseJobs:
    def __init__(self, sessions):
        self.sessions = sessions
        self.jobs = SqlPhaseJobs(sessions, "contract-worker", 30)
        self.team_id = uuid4()

    async def seed(self):
        async with self.sessions.begin() as session:
            if await session.get(Team, self.team_id) is None:
                session.add(Team(id=self.team_id, name=str(self.team_id), max_concurrent_tasks=4))
                await session.flush()
            task = Task(id=uuid4(), title="Adapter contract", team_id=self.team_id)
            session.add(task)
            await session.flush()
            await enqueue_phase(session, task)
            return task.id

    async def pause(self, task_id):
        async with self.sessions.begin() as session:
            task = await session.get(Task, task_id, with_for_update=True)
            await control_task(session, task, Action.PAUSE, actor="contract")

    async def expire(self, lease):
        async with self.sessions.begin() as session:
            job = await session.get(Job, lease.job_id, with_for_update=True)
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    async def snapshot(self, task_id):
        async with self.sessions() as session:
            task = await session.get(Task, task_id)
            actions = tuple(
                await session.scalars(
                    select(Job.action).where(Job.task_id == task_id, Job.state == JobState.QUEUED)
                )
            )
            return PhaseSnapshot(task.status, task.stage, task.lifecycle_version, actions)

    async def clean(self):
        async with self.sessions.begin() as session:
            await session.execute(delete(Task).where(Task.team_id == self.team_id))
            await session.execute(delete(Team).where(Team.id == self.team_id))


class PostgresOutbox:
    def __init__(self, sessions):
        self.sessions = sessions
        self.outbox = SqlEventOutbox(sessions)
        self.task_id = uuid4()

    async def seed(self):
        async with self.sessions.begin() as session:
            row = NotificationOutbox(id=uuid4(), task_id=self.task_id, revision=1)
            session.add(row)
            return row.id

    async def make_due(self, event_id):
        async with self.sessions.begin() as session:
            row = await session.get(NotificationOutbox, event_id, with_for_update=True)
            row.available_at = datetime.now(UTC) - timedelta(seconds=1)

    async def is_published(self, event_id):
        async with self.sessions() as session:
            row = await session.get(NotificationOutbox, event_id)
            return row.published_at is not None

    async def clean(self):
        async with self.sessions.begin() as session:
            await session.execute(
                delete(NotificationOutbox).where(NotificationOutbox.task_id == self.task_id)
            )


@pytest_asyncio.fixture
async def phase_jobs_contract(postgres_session_factory):
    harness = PostgresPhaseJobs(postgres_session_factory)
    try:
        yield harness
    finally:
        await harness.clean()


@pytest_asyncio.fixture
async def outbox_contract(postgres_session_factory):
    harness = PostgresOutbox(postgres_session_factory)
    try:
        yield harness
    finally:
        await harness.clean()
