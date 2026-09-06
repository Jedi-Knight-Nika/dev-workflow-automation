import pytest

from app.application.discover_integrations import DiscoverIntegrations
from app.application.ports.integration_discovery import RepositoryDiscoveryView, WorkflowStateView


class FakeDiscoveryWorkflow:
    async def github_repositories(self) -> list[RepositoryDiscoveryView]:
        return [RepositoryDiscoveryView("1", "owner", "repo", "owner/repo", "url", "main", True)]

    async def linear_workflow_states(self) -> list[WorkflowStateView]:
        return [WorkflowStateView("1", "Todo", "unstarted", "t", "Team", "TEAM")]


@pytest.mark.asyncio
async def test_integration_discovery_delegates_both_catalogs() -> None:
    discovery = DiscoverIntegrations(FakeDiscoveryWorkflow())
    assert (await discovery.github_repositories())[0].full_name == "owner/repo"
    assert (await discovery.linear_workflow_states())[0].team_key == "TEAM"
