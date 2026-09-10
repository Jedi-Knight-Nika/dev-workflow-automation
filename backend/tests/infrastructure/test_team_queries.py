from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.teams.infrastructure.management import SqlAlchemyTeamManagementWorkflow
from app.teams.infrastructure.profiles import SqlTeamProfiles


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [None, "CANCELLED", "RUNNING"])
async def test_assignment_views_only_load_tasks_for_active_assignments(status):
    team_id, task_id = uuid4(), uuid4()
    record = SimpleNamespace(
        id=uuid4(),
        task_id=task_id,
        team_id=team_id,
        status=status,
        queue_position=1,
        reason="test",
        assigned_at=datetime.now(UTC),
        started_at=None,
        completed_at=None,
    )
    session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                Mock(all=Mock(return_value=[record] if status else [])),
                [SimpleNamespace(id=task_id, team_id=team_id, status="ACTIVE", started_at=None)],
            ]
        )
    )
    views = await SqlAlchemyTeamManagementWorkflow(session).assignments(team_id)
    assert session.scalars.await_count == (2 if status == "RUNNING" else 1)
    if status:
        assert views[0].status == ("ACTIVE" if status == "RUNNING" else status)
    else:
        assert views == []


@pytest.mark.asyncio
@pytest.mark.parametrize("active", [False, True])
async def test_active_job_guard_uses_existence_with_same_states(active):
    task_id = uuid4()
    session = SimpleNamespace(scalar=AsyncMock(return_value=active))
    assert await SqlAlchemyTeamManagementWorkflow(session)._has_active_task_jobs(task_id) is active
    sql = str(session.scalar.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "EXISTS" in sql and "count(" not in sql
    assert "CLAIMED" in sql and "RUNNING" in sql and "QUEUED" not in sql


@pytest.mark.asyncio
async def test_profile_initialization_reuses_locked_team_check():
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=object()),
        scalars=AsyncMock(return_value=[]),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )
    assert await SqlTeamProfiles(session).initialize(uuid4(), ()) == []
    session.scalar.assert_awaited_once()
    assert "FOR UPDATE" in str(session.scalar.call_args.args[0])
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_list_still_rejects_missing_team():
    session = SimpleNamespace(scalar=AsyncMock(return_value=None), scalars=AsyncMock())
    with pytest.raises(LookupError, match="Team not found"):
        await SqlTeamProfiles(session).list_profiles(uuid4())
    session.scalars.assert_not_awaited()
