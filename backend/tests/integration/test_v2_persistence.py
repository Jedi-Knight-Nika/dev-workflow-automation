from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.lifecycle import LifecycleConflict, record_transition
from app.engineering.infrastructure.models import TaskPhaseRun
from app.engineering.infrastructure.task_models import Task, TaskEvent
from app.teams.application.profiles import ManageProfiles, ProfileConflict
from app.teams.domain.profiles import RoleKind
from app.teams.infrastructure.profiles import SqlTeamProfiles
from app.teams.infrastructure.team_models import Team

pytestmark = pytest.mark.asyncio


async def test_profile_roundtrip_and_optimistic_lock(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    team_id = uuid4()
    try:
        async with postgres_session_factory() as session:
            session.add(Team(id=team_id, name=f"v2-profiles-{team_id}"))
            await session.commit()
            store = SqlTeamProfiles(session)
            rows = await ManageProfiles(store).initialize(team_id)
            assert len(rows) == 4
            assert len(await ManageProfiles(store).initialize(team_id)) == 4
            developer = next(row for row in rows if row.profile.role_kind == RoleKind.DEVELOPER)
            saved = await ManageProfiles(store).save(
                team_id, RoleKind.DEVELOPER, replace(developer.profile, display_name="Sam"), 1
            )
            assert saved.version == 2
            assert saved.profile.display_name == "Sam"
            with pytest.raises(ProfileConflict):
                await ManageProfiles(store).save(team_id, RoleKind.DEVELOPER, developer.profile, 1)
            await session.rollback()
        async with postgres_session_factory() as session:
            rows = await SqlTeamProfiles(session).list_profiles(team_id)
            assert (
                next(
                    row for row in rows if row.profile.role_kind == RoleKind.DEVELOPER
                ).profile.display_name
                == "Sam"
            )
    finally:
        async with postgres_session_factory.begin() as session:
            await session.execute(delete(Team).where(Team.id == team_id))


async def test_transition_audit_and_version_are_atomic(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task_id = uuid4()
    try:
        async with postgres_session_factory.begin() as session:
            session.add(
                Task(
                    id=task_id,
                    title="V2 transition test",
                    status="NEW",
                    stage="INTAKE",
                    wait_reason="NONE",
                )
            )
        async with postgres_session_factory.begin() as session:
            await record_transition(
                session, task_id, Action.START, expected_version=1, actor="test-controller"
            )
        async with postgres_session_factory() as session:
            task = await session.get(Task, task_id)
            assert task is not None and task.stage == "DEVELOPING" and task.lifecycle_version == 2
            event = await session.scalar(select(TaskEvent).where(TaskEvent.task_id == task_id))
            assert event is not None and event.payload["actor"] == "test-controller"
            assert event.payload["from_status"] == "NEW"
            assert await session.scalar(select(TaskPhaseRun).where(TaskPhaseRun.task_id == task_id))
            with pytest.raises(LifecycleConflict):
                await record_transition(
                    session, task_id, Action.PAUSE, expected_version=1, actor="operator"
                )
    finally:
        async with postgres_session_factory.begin() as session:
            await session.execute(delete(Task).where(Task.id == task_id))
