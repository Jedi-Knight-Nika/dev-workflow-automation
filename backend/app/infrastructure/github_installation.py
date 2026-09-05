import json

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.github_installation import (
    GitHubAppSlugInvalid,
    GitHubInstallationNotConfigured,
    GitHubInstallationResult,
    GitHubInstallationStateInvalid,
)
from app.config import Settings
from app.db.models import Integration, IntegrationStatus
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import (
    create_install_state,
    github_app_install_url,
    resolve_github_auth,
    verify_install_state,
)


class EncryptedGitHubInstallationWorkflow:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def _integration(self) -> Integration | None:
        integration: Integration | None = await self._session.scalar(
            select(Integration).where(Integration.provider_name == "github")
        )
        return integration

    async def install_url(self) -> str:
        integration = await self._integration()
        slug = integration.configuration.get("app_slug") if integration else None
        if not integration or not integration.encrypted_credentials or not isinstance(slug, str):
            raise GitHubInstallationNotConfigured("Save GitHub App credentials and slug first")
        try:
            return github_app_install_url(slug, create_install_state(self._settings.app_secret_key))
        except ValueError as exc:
            raise GitHubAppSlugInvalid(str(exc)) from exc

    async def complete(self, installation_id: str, state: str) -> GitHubInstallationResult:
        if not verify_install_state(self._settings.app_secret_key, state):
            raise GitHubInstallationStateInvalid("Invalid or expired GitHub installation state")
        integration = await self._integration()
        if integration is None or integration.encrypted_credentials is None:
            raise GitHubInstallationNotConfigured("GitHub App credentials are not configured")
        try:
            credential = json.loads(cipher.decrypt(integration.encrypted_credentials))
            if not isinstance(credential, dict) or credential.get("auth_type") != "github_app":
                raise ValueError("GitHub integration is not configured as an App")
            credential["installation_id"] = installation_id
            integration.encrypted_credentials = cipher.encrypt(json.dumps(credential))
            auth = await resolve_github_auth(json.dumps(credential))
            await GitHubClient(auth.token, auth.installation).list_repositories()
        except (httpx.HTTPError, TypeError, ValueError, json.JSONDecodeError) as exc:
            integration.status = IntegrationStatus.ERROR
            integration.last_error = str(exc)[:2000]
            await self._session.commit()
            return GitHubInstallationResult(
                f"{self._settings.github_app_return_url}?github=error", False
            )
        integration.status = IntegrationStatus.CONNECTED
        integration.last_error = None
        await self._session.commit()
        return GitHubInstallationResult(
            f"{self._settings.github_app_return_url}?github=connected", True
        )
