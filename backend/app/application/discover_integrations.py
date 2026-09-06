from app.application.ports.integration_discovery import (
    IntegrationDiscoveryWorkflow,
    LinearMemberView,
    RepositoryDiscoveryView,
    TrelloBoardView,
    TrelloListView,
    WorkflowStateView,
)


class DiscoverIntegrations:
    def __init__(self, workflow: IntegrationDiscoveryWorkflow) -> None:
        self._workflow = workflow

    async def github_repositories(self) -> list[RepositoryDiscoveryView]:
        return await self._workflow.github_repositories()

    async def linear_workflow_states(self) -> list[WorkflowStateView]:
        return await self._workflow.linear_workflow_states()

    async def linear_members(self) -> list[LinearMemberView]:
        return await self._workflow.linear_members()

    async def trello_boards(self) -> list[TrelloBoardView]:
        return await self._workflow.trello_boards()

    async def trello_lists(self, board_id: str) -> list[TrelloListView]:
        return await self._workflow.trello_lists(board_id)
