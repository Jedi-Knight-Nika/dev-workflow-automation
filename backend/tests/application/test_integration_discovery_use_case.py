import pytest

from app.application.discover_integrations import DiscoverIntegrations
from app.application.ports.integration_discovery import (
    RepositoryDiscoveryView,
    TrelloBoardView,
    TrelloListView,
    WorkflowStateView,
)


class FakeDiscoveryWorkflow:
    async def github_repositories(self) -> list[RepositoryDiscoveryView]:
        return [RepositoryDiscoveryView("1", "owner", "repo", "owner/repo", "url", "main", True)]

    async def linear_workflow_states(self) -> list[WorkflowStateView]:
        return [WorkflowStateView("1", "Todo", "unstarted", "t", "Team", "TEAM")]

    async def trello_boards(self) -> list[TrelloBoardView]:
        return [TrelloBoardView("board-1", "Work", "https://trello.test/board")]

    async def trello_lists(self, board_id: str) -> list[TrelloListView]:
        assert board_id == "board-1"
        return [TrelloListView("list-1", "Ready", False)]


@pytest.mark.asyncio
async def test_integration_discovery_delegates_catalogs() -> None:
    discovery = DiscoverIntegrations(FakeDiscoveryWorkflow())
    assert (await discovery.github_repositories())[0].full_name == "owner/repo"
    assert (await discovery.linear_workflow_states())[0].team_key == "TEAM"
    assert (await discovery.trello_boards())[0].name == "Work"
    assert (await discovery.trello_lists("board-1"))[0].name == "Ready"
