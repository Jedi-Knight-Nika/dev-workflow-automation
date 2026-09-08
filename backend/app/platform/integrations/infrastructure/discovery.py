from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.infrastructure.github_client import GitHubClient
from app.intake.infrastructure.linear_client import LinearClient
from app.intake.infrastructure.trello_client import TrelloClient
from app.platform.integrations.application.ports.integration_discovery import (
    IntegrationNotConfigured,
    LinearMemberView,
    RepositoryDiscoveryView,
    TrelloBoardView,
    TrelloListView,
    WorkflowStateView,
)
from app.platform.integrations.github_auth import resolve_github_auth
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher


class EncryptedIntegrationDiscoveryWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _credential(self, provider: str) -> str:
        integration = await self._session.scalar(
            select(Integration).where(Integration.provider_name == provider)
        )
        if integration is None or integration.encrypted_credentials is None:
            raise IntegrationNotConfigured(f"Configure {provider.title()} credentials first")
        return cipher.decrypt(integration.encrypted_credentials)

    async def github_repositories(self) -> list[RepositoryDiscoveryView]:
        auth = await resolve_github_auth(await self._credential("github"))
        repositories = await GitHubClient(auth.token, auth.installation).list_repositories()
        return [
            RepositoryDiscoveryView(
                item.external_repo_id,
                item.owner,
                item.name,
                item.full_name,
                item.clone_url,
                item.default_branch,
                item.private,
            )
            for item in repositories
        ]

    async def linear_workflow_states(self) -> list[WorkflowStateView]:
        states = await LinearClient(await self._credential("linear")).list_workflow_states()
        return [
            WorkflowStateView(
                state["id"],
                state["name"],
                state["type"],
                state["team_id"],
                state["team_name"],
                state["team_key"],
            )
            for state in states
        ]

    async def linear_members(self) -> list[LinearMemberView]:
        members = await LinearClient(await self._credential("linear")).list_members()
        return [
            LinearMemberView(member["id"], member["name"], member["email"], member["active"])
            for member in members
        ]

    async def trello_boards(self) -> list[TrelloBoardView]:
        boards = await TrelloClient(await self._credential("trello")).list_boards()
        return [TrelloBoardView(item["id"], item["name"], item["url"]) for item in boards]

    async def trello_lists(self, board_id: str) -> list[TrelloListView]:
        lists = await TrelloClient(await self._credential("trello")).list_lists(board_id)
        return [TrelloListView(item["id"], item["name"], item["closed"]) for item in lists]
