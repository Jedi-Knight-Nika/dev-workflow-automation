from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.provider_catalog import (
    ProviderCatalogView,
    ProviderModelView,
    ProviderNotConfigured,
    ProviderNotSupported,
)
from app.db.models import Integration
from app.infrastructure.security.crypto import cipher
from app.providers import create_provider


class EncryptedProviderCatalogWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def discover(self, provider_name: str) -> ProviderCatalogView:
        integration = await self._session.scalar(
            select(Integration).where(Integration.provider_name == provider_name)
        )
        if integration is None or integration.encrypted_credentials is None:
            raise ProviderNotConfigured(f"Configure {provider_name} credentials first")
        try:
            provider = create_provider(
                provider_name, cipher.decrypt(integration.encrypted_credentials)
            )
        except ValueError as exc:
            raise ProviderNotSupported(str(exc)) from exc
        models = await provider.list_models()
        return ProviderCatalogView(
            provider_name,
            provider.capabilities(),
            [ProviderModelView(model.id, model.display_name) for model in models],
        )
