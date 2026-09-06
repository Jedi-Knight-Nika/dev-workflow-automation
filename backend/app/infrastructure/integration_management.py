import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.integration_management import (
    ConfigureIntegrationCommand,
    IntegrationView,
    ManagedIntegrationNotConfigured,
)
from app.db.models import Integration, IntegrationStatus
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth
from app.integrations.linear import LinearClient
from app.integrations.trello import TrelloClient
from app.providers import create_provider


def integration_to_view(item: Integration) -> IntegrationView:
    return IntegrationView(
        item.id,
        item.provider_type,
        item.provider_name,
        item.status.value,
        item.configuration,
        item.encrypted_credentials is not None,
        item.last_error,
        item.sync_status,
        item.last_synced_at,
        item.updated_at,
    )


class EncryptedIntegrationManagementWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get(self, name: str) -> Integration | None:
        result: Integration | None = await self._session.scalar(
            select(Integration).where(Integration.provider_name == name)
        )
        return result

    async def list(self) -> list[IntegrationView]:
        items = (
            await self._session.scalars(select(Integration).order_by(Integration.provider_name))
        ).all()
        return [integration_to_view(item) for item in items]

    async def configure(self, command: ConfigureIntegrationCommand) -> IntegrationView:
        item = await self._get(command.provider_name)
        if item is None:
            item = Integration(
                provider_name=command.provider_name, provider_type=command.provider_type
            )
            self._session.add(item)
        item.provider_type = command.provider_type
        item.status = IntegrationStatus(command.status)
        item.configuration = command.configuration
        if command.credential is not None:
            item.encrypted_credentials = cipher.encrypt(command.credential)
        item.last_error = None
        await self._session.commit()
        await self._session.refresh(item)
        return integration_to_view(item)

    async def verify(self, provider_name: str) -> IntegrationView:
        item = await self._get(provider_name)
        if item is None or item.encrypted_credentials is None:
            raise ManagedIntegrationNotConfigured("Configure credentials first")
        credential = cipher.decrypt(item.encrypted_credentials)
        try:
            if provider_name == "github":
                auth = await resolve_github_auth(credential)
                await GitHubClient(auth.token, auth.installation).list_repositories()
            elif provider_name == "linear":
                await LinearClient(credential).list_workflow_states()
            elif provider_name == "trello":
                await TrelloClient(credential).list_boards()
            elif provider_name in {"openai", "anthropic", "google"}:
                await create_provider(provider_name, credential).list_models()
            elif provider_name in {"npm_registry", "pypi_registry"}:
                if not credential.strip():
                    raise ValueError("Registry token cannot be empty")
            else:
                raise ValueError(f"Unsupported integration: {provider_name}")
        except (httpx.HTTPError, RuntimeError, TypeError, ValueError) as exc:
            item.status, item.last_error = IntegrationStatus.ERROR, str(exc)[:2000]
        else:
            item.status, item.last_error = IntegrationStatus.CONNECTED, None
        await self._session.commit()
        return integration_to_view(item)
