import uuid

import pytest

from app.application.manage_teams import ManageTeams
from app.application.ports.team_management import SaveTeamCommand, TeamNotFound
from app.domain.teams import Team


def test_team_domain_enforces_identity_and_concurrency() -> None:
    with pytest.raises(ValueError, match="blank"):
        Team(uuid.uuid4(), "  ")
    with pytest.raises(ValueError, match="concurrency"):
        Team(uuid.uuid4(), "Builders", max_concurrent_tasks=0)


class EmptyTeams:
    async def get(self, team_id: uuid.UUID) -> None:
        return None


@pytest.mark.asyncio
async def test_get_team_translates_missing_port_result() -> None:
    with pytest.raises(TeamNotFound):
        await ManageTeams(EmptyTeams()).get(uuid.uuid4())  # type: ignore[arg-type]


def test_save_team_command_has_safe_sequential_default() -> None:
    assert SaveTeamCommand("Builders").max_concurrent_tasks == 1
