from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.teams.application.ports.team_management import SaveTeamCommand
from app.teams.domain.profiles import default_profiles
from app.teams.infrastructure.automation import read_policy
from app.teams.infrastructure.management import SqlAlchemyTeamManagementWorkflow
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.profiles import SqlTeamProfiles
from app.teams.infrastructure.team_models import Team


@pytest.mark.asyncio
async def test_new_team_has_fixed_profiles_and_disabled_policy_atomically(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    team_id = None
    try:
        async with postgres_session_factory() as session:
            created = await SqlAlchemyTeamManagementWorkflow(session).create(
                SaveTeamCommand(name=f"initial-team-{uuid4()}")
            )
            team_id = created.id
        async with postgres_session_factory() as session:
            profiles = list(
                await session.scalars(
                    select(TeamAgentProfile).where(TeamAgentProfile.team_id == team_id)
                )
            )
            assert {row.role_kind for row in profiles} == {
                "INTERPRETER",
                "DEVELOPER",
                "THINKER",
                "REVIEWER",
            }
            assert all(row.hard_budget_usd is None for row in profiles)
            assert not any(
                row.enabled for row in profiles if row.role_kind in {"THINKER", "REVIEWER"}
            )
            policy = await read_policy(session, team_id)
            assert not policy.enrollment_enabled and not policy.auto_merge
            assert policy.repository_ids == ()
            developer = next(row for row in profiles if row.role_kind == "DEVELOPER")
            developer.model = "operator-configured"
            await session.commit()
            await SqlTeamProfiles(session).initialize(team_id, default_profiles())
            await session.refresh(developer)
            assert developer.model == "operator-configured"
            assert len(await SqlTeamProfiles(session).list_profiles(team_id)) == 4
    finally:
        if team_id:
            async with postgres_session_factory.begin() as session:
                await session.execute(delete(Team).where(Team.id == team_id))
