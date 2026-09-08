from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.usage import Usage
from app.agent_runtime.infrastructure.helper_accounting import SqlHelperStore
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.engineering.domain.lifecycle import Action, InvalidTransition
from app.engineering.infrastructure.controls import control_task
from app.engineering.infrastructure.history import SqlAlchemyTaskHistoryQueries
from app.engineering.infrastructure.jobs import SqlPhaseJobs
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.platform.scheduling.states import JobState
from app.teams.infrastructure.management import SqlAlchemyTeamManagementWorkflow
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team
from tests.integration.test_v2_enrollment_and_costs import scenario

pytestmark = pytest.mark.asyncio


async def test_new_start_is_idempotent_and_team_shutdown_is_not_deactivation(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (team_id, _, task_id, _):
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id, with_for_update=True)
            assert task
            await control_task(session, task, Action.RESUME, actor="operator")
            await control_task(session, task, Action.RESUME, actor="operator")
            assert len(list(await session.scalars(select(Job).where(Job.task_id == task_id)))) == 1
        jobs = SqlPhaseJobs(postgres_session_factory, "control-test", 60)
        lease = await jobs.claim()
        assert lease
        async with postgres_session_factory() as session:
            await SqlAlchemyTeamManagementWorkflow(session).shutdown(team_id)
        assert not await jobs.heartbeat(lease)
        assert await jobs.claim() is None
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id, with_for_update=True)
            team = await session.get(Team, team_id)
            assert task and team and team.enabled and team.execution_paused
            assert task.status == "PAUSED"
            with pytest.raises(InvalidTransition, match="Enable execution"):
                await control_task(session, task, Action.RESUME, actor="operator")
        async with postgres_session_factory() as session:
            await SqlAlchemyTeamManagementWorkflow(session).wake(team_id)
        assert await jobs.claim() is None  # Wake does not resume paused tickets.
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id, with_for_update=True)
            assert task and task.status == "PAUSED"
            await control_task(session, task, Action.RESUME, actor="operator")
        assert await jobs.claim() is not None


async def test_plan_handoff_has_own_receipt_and_keeps_developer_session(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (team_id, _, task_id, _):
        jobs = SqlPhaseJobs(postgres_session_factory, "helper-test", 60)
        intake = await jobs.claim()
        assert intake
        await jobs.complete(intake, Action.START)
        developer = await jobs.claim()
        assert developer
        await jobs.complete(developer, Action.NEEDS_PLAN)
        thinker = await jobs.claim()
        assert thinker and thinker.action == "THINKER_TURN"
        async with postgres_session_factory.begin() as session:
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            assert native
            native.native_session_id = "developer-native"
            profile = TeamAgentProfile(
                team_id=team_id,
                role_kind="THINKER",
                display_name="Thinker",
                provider="anthropic",
                model="unit-model",
                harness="claude",
                hard_budget_usd=Decimal("0.5"),
            )
            session.add(profile)
            await session.flush()
        store = SqlHelperStore(postgres_session_factory, thinker, profile, Decimal("0.5"), None)
        run_id = await store.begin_run(task_id, 1)
        await store.session_started(task_id, "helper-native")
        receipt = TurnReceipt(
            "helper-native",
            "turn-1",
            "PLAN_READY\nUse the existing API.",
            "completed",
            Usage(100, 20, 0, 0, provider_cost_usd=Decimal("0.01")),
        )
        await store.finish_run(run_id, receipt)
        await store.finish_run(run_id, receipt)
        await jobs.complete(thinker, Action.PLAN_READY)
        async with postgres_session_factory() as session:
            task = await session.get(Task, task_id)
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            row = await session.get(AIRun, run_id)
            assert task and task.stage == "DEVELOPING"
            assert native and native.native_session_id == "developer-native"
            assert row and row.session_id is None and row.native_session_id == "helper-native"
            runs = await SqlAlchemyTaskHistoryQueries(session).runs(task_id)
            assert len(runs) == 1 and runs[0].artifact == receipt.summary
            assert Decimal(runs[0].cost_usd or "0") == Decimal("0.01")
            events = list(
                await session.scalars(
                    select(TaskEvent).where(
                        TaskEvent.task_id == task_id,
                        TaskEvent.event_type == "TASK_LIFECYCLE_CHANGED",
                    )
                )
            )
            assert [event.payload["action"] for event in events] == [
                "START",
                "NEEDS_PLAN",
                "PLAN_READY",
            ]
            assert all(
                event.created_at and event.payload["actor"] == "helper-test" for event in events
            )


async def test_full_team_does_not_starve_other_team(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path / "a") as (first_team, _, first_task, _):  # noqa: SIM117
        async with scenario(postgres_session_factory, tmp_path / "b") as (_, _, second_task, _):
            async with postgres_session_factory.begin() as session:
                team = await session.get(Team, first_team)
                assert team
                team.max_concurrent_tasks = 1
                session.add(
                    Job(
                        task_id=first_task,
                        action="DEVELOPER_TURN",
                        state=JobState.RUNNING,
                        lease_token=uuid4(),
                        lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
                    )
                )
            lease = await SqlPhaseJobs(postgres_session_factory, "fair-test", 60).claim()
            assert lease and lease.task_id == second_task
