import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.model_validation import ModelValidationResult
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

    async def validate(self, provider_name: str, model: str) -> ModelValidationResult:
        try:
            catalog = await self.discover(provider_name)
        except ProviderNotConfigured as exc:
            return ModelValidationResult("UNAUTHORIZED", str(exc))
        except ProviderNotSupported as exc:
            return ModelValidationResult("ERROR", str(exc))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                return ModelValidationResult("UNAUTHORIZED", "Provider rejected this credential")
            return ModelValidationResult(
                "ERROR", f"Provider returned HTTP {exc.response.status_code}"
            )
        except httpx.HTTPError as exc:
            return ModelValidationResult("ERROR", f"Provider check failed: {exc}")
        if any(item.id == model for item in catalog.models):
            return ModelValidationResult("AVAILABLE", "Model is available for this credential")
        return ModelValidationResult("MODEL_NOT_FOUND", "Provider did not return this model ID")
