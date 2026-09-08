from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.application.sessions import ChangeSession, SessionConflict, SessionView
from app.agent_runtime.domain.session_changes import SessionChangeMode
from app.agent_runtime.infrastructure.accounting import SqlDevelopmentStore
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.agent_runtime.infrastructure.sessions import SqlSessionAdministration
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.controls import control_task
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.platform.scheduling.states import JobState
from app.teams.infrastructure.models import TeamAgentProfile
from tests.integration.test_enrollment_and_costs import scenario

pytestmark = pytest.mark.asyncio


def command(
    view: SessionView, mode: SessionChangeMode = SessionChangeMode.KEEP_NATIVE
) -> ChangeSession:
    return ChangeSession(
        view.session_id,
        view.lifecycle_version,
        view.profile_version,
        mode,
        "Operator selected another model",
    )


async def prepare(session: AsyncSession, task_id):
    task = await session.get(Task, task_id)
    assert task
    await control_task(session, task, Action.PAUSE, actor="test")
    native = await session.scalar(
        select(DeveloperSession).where(DeveloperSession.task_id == task_id)
    )
    assert native
    native.native_session_id, native.state = "existing-thread", "READY"
    native.last_revision = "a" * 40
    native.checkpoint = {
        "summary": "Work already completed",
        "base_sha": "b" * 40,
        "base_branch": "main",
        "next_feedback": "Fix failing assertion",
        "cumulative_usage": {"input_tokens": 400, "output_tokens": 10},
        "transcript": "Never replay this",
        "compacted_input_tokens": 300,
    }
    profile = await session.get(TeamAgentProfile, native.profile_id)
    assert profile
    profile.model, profile.version = "unit-new-model", 2
    run = AIRun(
        task_id=task_id,
        session_id=native.id,
        role_kind="DEVELOPER",
        provider=native.provider,
        model=native.model,
        status="SUCCEEDED",
        prompt_version="fixed",
        calculated_cost_usd=Decimal("0.10"),
        input_tokens=400,
        output_tokens=10,
    )
    session.add(run)
    await session.commit()
    return task, native, profile, run


async def test_keep_thread_preserves_usage_records_and_requires_separate_resume(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with (
        scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _),
        postgres_session_factory() as session,
    ):
        task, native, _, run = await prepare(session, task_id)
        store = SqlSessionAdministration(session)
        before = await store.read(task_id)
        assert before and not before.blocker
        change = command(before)
        after = await store.change(task_id, change)
        await session.refresh(native)
        assert after.session_id == native.id == before.session_id
        assert after.model == "unit-new-model" and after.generation == 1
        assert after.task_status == task.status == "PAUSED"
        assert after.lifecycle_version == before.lifecycle_version + 1
        assert native.native_session_id == "existing-thread"
        assert native.checkpoint["cumulative_usage"]["input_tokens"] == 400
        assert "Fix failing assertion" in native.checkpoint["next_feedback"]
        assert "Operator model change" in native.checkpoint["next_feedback"]
        await session.refresh(run)
        assert run.model == "gpt-5.6-terra" and run.calculated_cost_usd == Decimal("0.10")
        assert not await session.scalar(
            select(Job.id).where(Job.task_id == task_id, Job.state == JobState.QUEUED)
        )
        event = await session.scalar(
            select(TaskEvent).where(
                TaskEvent.task_id == task_id,
                TaskEvent.event_type == "DEVELOPER_SESSION_CHANGED",
            )
        )
        assert event and event.source == "user" and event.payload["usage_reset"] is False
        assert "existing-thread" not in str(event.payload)
        with pytest.raises(SessionConflict, match="reload"):
            await store.change(task_id, change)


async def test_cross_harness_handoff_uses_same_checkout_but_not_native_id_or_usage_baseline(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with (
        scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _),
        postgres_session_factory() as session,
    ):
        _, previous, profile, run = await prepare(session, task_id)
        profile.harness, profile.provider, profile.model = "claude", "anthropic", "unit-claude"
        await session.commit()
        store = SqlSessionAdministration(session)
        before = await store.read(task_id)
        assert before and not before.keep_native_available
        with pytest.raises(SessionConflict, match="handoff"):
            await store.change(task_id, command(before))
        after = await store.change(task_id, command(before, SessionChangeMode.HANDOFF))
        assert after.generation == 2 and after.session_id != previous.id
        assert after.task_status == "PAUSED" and not after.has_native_session
        successor = await session.get(DeveloperSession, after.session_id)
        assert successor and successor.profile_id == profile.id
        assert successor.state == "CREATED" and previous.state == "SUPERSEDED"
        assert previous.native_session_id == "existing-thread"
        assert successor.workspace_path == previous.workspace_path
        assert successor.state_path == previous.state_path
        assert successor.last_revision == previous.last_revision
        assert set(successor.checkpoint) == {
            "base_sha",
            "base_branch",
            "next_feedback",
            "handoff",
        }
        assert successor.checkpoint["handoff"]["summary"] == "Work already completed"
        assert (await store.read(task_id)).session_id == successor.id
        assert (await session.get(AIRun, run.id)).session_id == previous.id
        assert not await session.scalar(
            select(Job.id).where(Job.task_id == task_id, Job.state == JobState.QUEUED)
        )
        jobs = await session.scalars(select(Job).where(Job.task_id == task_id))
        accounting = SqlDevelopmentStore(
            postgres_session_factory,
            session_id=successor.id,
            job_id=jobs.first().id,
            lease_token="not-used",
        )
        assert await accounting.consumed_cost(task_id) == Decimal("0.10")
        assert not Path(successor.workspace_path).exists()  # Metadata change never edits files.


@pytest.mark.parametrize(
    "blocker",
    [
        "active_task",
        "active_worker",
        "running_receipt",
        "unknown_cost",
        "takeover",
        "stale_profile",
        "stale_session",
        "disabled_profile",
    ],
)
async def test_unsafe_or_stale_session_changes_are_refused_without_mutation(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path, blocker: str
) -> None:
    async with (
        scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _),
        postgres_session_factory() as session,
    ):
        task, native, profile, run = await prepare(session, task_id)
        store = SqlSessionAdministration(session)
        before = await store.read(task_id)
        assert before
        request = command(before)
        if blocker == "active_task":
            task.status = "ACTIVE"
        elif blocker == "active_worker":
            native.state = "RUNNING"
        elif blocker == "running_receipt":
            run.status = "RUNNING"
        elif blocker == "unknown_cost":
            run.calculated_cost_usd = None
        elif blocker == "takeover":
            task.manual_takeover = True
        elif blocker == "stale_profile":
            profile.version += 1
        elif blocker == "stale_session":
            request = replace(request, lifecycle_version=before.lifecycle_version - 1)
        else:
            profile.enabled = False
        await session.commit()
        with pytest.raises(SessionConflict):
            await store.change(task_id, request)
        await session.rollback()
        await session.refresh(native)
        assert native.model == "gpt-5.6-terra" and native.native_session_id == "existing-thread"
        assert not await session.scalar(
            select(TaskEvent.id).where(
                TaskEvent.task_id == task_id,
                TaskEvent.event_type == "DEVELOPER_SESSION_CHANGED",
            )
        )
