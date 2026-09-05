from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.integration_discovery import (
    IntegrationNotConfigured,
    RepositoryDiscoveryView,
    WorkflowStateView,
)
from app.db.models import Integration
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth
from app.integrations.linear import LinearClient


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
