from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

from app.analytics.infrastructure.forecast_worker import SNAPSHOT_BATCH_SIZE, snapshot_forecasts
from app.analytics.infrastructure.models import TaskForecast
from app.coordinator.infrastructure.models import CoordinatorAction, CoordinatorRun
from app.coordinator.infrastructure.processor import SqlCoordinationRuns
from app.engineering.infrastructure.task_models import Task
from app.intake.infrastructure.task_snapshot import ExternalTaskSnapshot
from app.platform.configuration.settings import Settings
from tests.integration.test_coordinator import choice


async def test_team_shutdown_handles_multiple_batches_without_resuming_them(
    postgres_session_factory, tmp_path
):
    from app.teams.infrastructure.management import SqlAlchemyTeamManagementWorkflow
    from tests.integration.test_enrollment_and_costs import scenario

    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (team_id, repo_id, _, _):
        async with factory.begin() as session:
            session.add_all(
                [
                    Task(title="Batched shutdown", team_id=team_id, repository_id=repo_id)
                    for _ in range(51)
                ]
            )
        async with factory() as session:
            result = await SqlAlchemyTeamManagementWorkflow(session).shutdown(team_id)
            assert result.paused_tasks == 52
        async with factory() as session:
            await SqlAlchemyTeamManagementWorkflow(session).wake(team_id)
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Task)
                    .where(Task.team_id == team_id, Task.status == "PAUSED")
                )
                == 52
            )


async def test_forecast_pass_is_bounded_and_resumes_beyond_5000_tasks(postgres_session_factory):
    factory = postgres_session_factory
    identifiers = [UUID(int=100000 + offset) for offset in range(5001)]
    try:
        async with factory.begin() as session:
            await session.execute(
                Task.__table__.insert(),
                [
                    {"id": identifier, "title": "Forecast scale fixture"}
                    for identifier in identifiers
                ],
            )
        cursor = await snapshot_forecasts(factory, minimum=5)
        assert cursor == identifiers[SNAPSHOT_BATCH_SIZE - 1]
        next_cursor = await snapshot_forecasts(factory, minimum=5, after=cursor)
        assert next_cursor == identifiers[2 * SNAPSHOT_BATCH_SIZE - 1]
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(TaskForecast)
                    .where(TaskForecast.task_id.in_(identifiers))
                )
                == 2 * SNAPSHOT_BATCH_SIZE
            )
    finally:
        async with factory.begin() as session:
            await session.execute(delete(TaskForecast).where(TaskForecast.task_id.in_(identifiers)))
            await session.execute(delete(Task).where(Task.id.in_(identifiers)))


@pytest.mark.parametrize("status", ["FAILED", "SUPERSEDED", "READY", "SHADOW"])
async def test_late_coordinator_completion_cannot_reopen_terminal_run(
    postgres_session_factory, status
):
    factory = postgres_session_factory
    task_id, run_id = uuid4(), uuid4()
    try:
        async with factory.begin() as session:
            session.add(Task(id=task_id, title="Late completion"))
            await session.flush()
            session.add(
                CoordinatorRun(
                    id=run_id,
                    task_id=task_id,
                    mode="active",
                    status=status,
                    lifecycle_revision=1,
                    requirement_revision=1,
                    evidence={},
                    decision={},
                    created_at=datetime.now(UTC),
                )
            )
        store = SqlCoordinationRuns(factory, Settings(_env_file=None))
        await store.complete(run_id, task_id, choice("IMPLEMENT"), {})
        async with factory() as session:
            assert (await session.get(CoordinatorRun, run_id)).status == status
            assert (
                await session.scalar(
                    select(CoordinatorAction.id).where(CoordinatorAction.run_id == run_id)
                )
                is None
            )
    finally:
        async with factory.begin() as session:
            await session.execute(delete(CoordinatorRun).where(CoordinatorRun.id == run_id))
            await session.execute(delete(Task).where(Task.id == task_id))


async def test_tracker_search_columns_follow_raw_payload_updates(postgres_session_factory):
    factory = postgres_session_factory
    task_id, snapshot_id = uuid4(), uuid4()
    try:
        async with factory.begin() as session:
            session.add(Task(id=task_id, title="Search fixture"))
            await session.flush()
            session.add(
                ExternalTaskSnapshot(
                    id=snapshot_id,
                    task_id=task_id,
                    provider="test",
                    external_id=str(snapshot_id),
                    identifier="fixture",
                    raw_payload={
                        "assignee": {"name": "Alice", "email": "alice@example.test"},
                        "labels": ["Backend"],
                        "description": "not-a-label",
                    },
                )
            )
        async with factory.begin() as session:
            snapshot = await session.get(ExternalTaskSnapshot, snapshot_id)
            assert snapshot.assignee_name == "Alice"
            assert "backend" in snapshot.labels_text
            assert "not-a-label" not in snapshot.labels_text
            snapshot.raw_payload = {"assignee": {"name": "Bob"}}
        async with factory() as session:
            snapshot = await session.get(ExternalTaskSnapshot, snapshot_id)
            assert snapshot.assignee_name == "Bob"
            assert snapshot.assignee_email is None
    finally:
        async with factory.begin() as session:
            await session.execute(delete(Task).where(Task.id == task_id))
