import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.activity.infrastructure.projector import ActivityProjector
from app.activity.infrastructure.queries import SqlActivityQueries
from app.coordinator.infrastructure.administration import CoordinationAdministration
from app.engineering.infrastructure.dependencies import SqlTaskDependencies
from app.engineering.infrastructure.job_queue import claim_next_job
from app.engineering.infrastructure.queries import SqlAlchemyTaskQueries
from app.engineering.infrastructure.task_models import Job, Task, TaskDependency, TaskEvent
from app.platform.configuration.settings import Settings
from app.platform.scheduling.states import JobState
from app.teams.infrastructure.team_models import Team
from tests.integration.test_activity import window


@pytest_asyncio.fixture
async def graph(postgres_session_factory):
    factory = postgres_session_factory
    team, first, second, third = (uuid4() for _ in range(4))
    async with factory.begin() as session:
        session.add(Team(id=team, name=f"Dependencies {team}"))
        await session.flush()
        session.add_all(Task(id=id, team_id=team, title=str(id)) for id in (first, second, third))
    try:
        yield factory, team, first, second, third
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(TaskDependency).where(TaskDependency.task_id.in_([first, second, third]))
            )
            await session.execute(delete(Task).where(Task.id.in_([first, second, third])))
            await session.execute(delete(Team).where(Team.id == team))


async def test_prerequisites_gate_dispatch_and_unblock_without_lifecycle_changes(graph):
    factory, team, first, second, third = graph
    await SqlTaskDependencies(factory).replace(first, (second,), ())
    async with factory.begin() as session:
        session.add_all(
            [
                Job(task_id=first, action="DEVELOPER_TURN"),
                Job(task_id=third, action="RUN_VALIDATION"),
            ]
        )
    async with factory() as session:
        job = await claim_next_job(session, "test", 30)
        assert job.task_id == third
    queue = await CoordinationAdministration(factory, Settings()).queue(team)
    assert (
        next(row for row in queue["entries"] if row["id"] == str(first))["lane"]
        == "WAITING_DEPENDENCY"
    )
    async with factory() as session:
        assert await claim_next_job(session, "test", 30) is None
        first_job = await session.scalar(select(Job).where(Job.task_id == first))
        assert first_job.attempt == 0 and first_job.state == JobState.QUEUED
        view = await SqlAlchemyTaskQueries(session).get(first)
        assert view.dependencies[0].id == second
    async with factory.begin() as session:
        prerequisite = await session.get(Task, second)
        prerequisite.status = "CANCELLED"
    async with factory() as session:
        assert await claim_next_job(session, "test", 30) is None
    async with factory.begin() as session:
        prerequisite = await session.get(Task, second)
        prerequisite.status, prerequisite.stage = "MERGED", "COMPLETE"
    async with factory() as session:
        job = await claim_next_job(session, "test", 30)
        assert job.task_id == first and job.attempt == 1
        task = await session.get(Task, first)
        assert task.lifecycle_version == 1 and task.status == "NEW"


async def test_dependency_edits_reject_cycles_stale_saves_and_active_work(graph):
    factory, _, first, second, third = graph
    service = SqlTaskDependencies(factory)
    await service.replace(first, (second,), ())
    await service.replace(second, (third,), ())
    with pytest.raises(ValueError, match="cycle"):
        await service.replace(third, (first,), ())
    with pytest.raises(ValueError, match="changed"):
        await service.replace(first, (), ())
    with pytest.raises(ValueError, match="itself"):
        await service.replace(third, (third,), ())
    with pytest.raises(LookupError):
        await service.replace(third, (uuid4(),), ())
    async with factory.begin() as session:
        task = await session.get(Task, first)
        task.status = "ACTIVE"
    with pytest.raises(ValueError, match="Pause"):
        await service.replace(first, (), (second,))
    async with factory.begin() as session:
        task = await session.get(Task, first)
        task.status = "PAUSED"
        session.add(Job(task_id=first, action="DEVELOPER_TURN", state=JobState.RUNNING))
    with pytest.raises(ValueError, match="execution"):
        await service.replace(first, (), (second,))


async def test_concurrent_graph_edits_and_claims_cannot_bypass_dependencies(graph):
    factory, _, first, second, third = graph
    service = SqlTaskDependencies(factory)
    results = await asyncio.gather(
        service.replace(first, (second,), ()),
        service.replace(second, (first,), ()),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ValueError) for result in results) == 1
    async with factory.begin() as session:
        session.add(Job(task_id=third, action="DEVELOPER_TURN"))

    async def claim():
        async with factory() as session:
            return await claim_next_job(session, "test", 30)

    edited, claimed = await asyncio.gather(
        service.replace(third, (first,), ()), claim(), return_exceptions=True
    )
    assert (edited is None and claimed is None) or (
        isinstance(edited, ValueError) and isinstance(claimed, Job)
    )


async def test_dependency_history_baseline_and_paused_task_remain_preserved(graph):
    factory, _, first, second, _ = graph
    await SqlTaskDependencies(factory).replace(first, (second,), ())
    now = datetime.now(UTC)
    async with factory.begin() as session:
        event = await session.scalar(select(TaskEvent).where(TaskEvent.task_id == first))
        event.created_at = now - timedelta(hours=2)
        session.add(TaskEvent(task_id=first, source="dashboard", event_type="TASK_CREATED"))
        task = await session.get(Task, first)
        task.status = "PAUSED"
        session.add(Job(task_id=first, action="DEVELOPER_TURN"))
        prerequisite = await session.get(Task, second)
        prerequisite.status, prerequisite.stage = "MERGED", "COMPLETE"
    await ActivityProjector(factory).project()
    queries = SqlActivityQueries(factory, 100, 20)
    selected = window(first, now - timedelta(hours=1))
    flight = await queries.preflight(selected)
    baseline = await queries.baseline(selected, flight["through_sequence"])
    assert baseline["tasks"][0]["dependency_ids"] == [str(second)]
    async with factory() as session:
        assert await claim_next_job(session, "test", 30) is None
