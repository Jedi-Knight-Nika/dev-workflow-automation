import json

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.github_installation import (
    GitHubAppSlugInvalid,
    GitHubInstallationAccount,
    GitHubInstallationNotConfigured,
    GitHubInstallationResult,
    GitHubInstallationStateInvalid,
)
from app.config import Settings
from app.db.models import Integration, IntegrationStatus
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import (
    create_app_jwt,
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

    def _private_key(self) -> str:
        if self._settings.github_app_private_key:
            return self._settings.github_app_private_key.replace("\\n", "\n")
        key_file = self._settings.github_app_private_key_file
        if key_file is not None:
            try:
                return key_file.read_text().strip()
            except OSError as exc:
                raise GitHubInstallationNotConfigured(
                    "The configured GitHub App private-key file cannot be read"
                ) from exc
        raise GitHubInstallationNotConfigured(
            "The server operator has not configured the GitHub App private key"
        )

    async def install_url(self) -> str:
        slug = self._settings.github_app_slug
        if not slug or not self._settings.github_app_id:
            raise GitHubInstallationNotConfigured(
                "The server operator has not configured the GitHub App"
            )
        self._private_key()
        try:
            return github_app_install_url(slug, create_install_state(self._settings.app_secret_key))
        except ValueError as exc:
            raise GitHubAppSlugInvalid(str(exc)) from exc

    async def manage_url(self) -> str:
        integration = await self._integration()
        if integration is None or integration.encrypted_credentials is None:
            raise GitHubInstallationNotConfigured("GitHub is not connected")
        try:
            credential = json.loads(cipher.decrypt(integration.encrypted_credentials))
            installation_id = str(credential.get("installation_id", ""))
        except (TypeError, json.JSONDecodeError) as exc:
            raise GitHubInstallationNotConfigured("GitHub installation is invalid") from exc
        if not installation_id.isdigit():
            raise GitHubInstallationNotConfigured("GitHub installation is invalid")
        return f"https://github.com/settings/installations/{installation_id}"

    async def account(self) -> GitHubInstallationAccount:
        integration = await self._integration()
        if integration is None or integration.encrypted_credentials is None:
            raise GitHubInstallationNotConfigured("GitHub is not connected")
        try:
            credential = json.loads(cipher.decrypt(integration.encrypted_credentials))
            app_id = str(credential.get("app_id", ""))
            installation_id = str(credential.get("installation_id", ""))
            private_key = str(credential.get("private_key", ""))
            jwt = create_app_jwt(app_id, private_key)
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"https://api.github.com/app/installations/{installation_id}",
                    headers={
                        "authorization": f"Bearer {jwt}",
                        "accept": "application/vnd.github+json",
                        "x-github-api-version": "2022-11-28",
                    },
                )
                response.raise_for_status()
                account = response.json()["account"]
            return GitHubInstallationAccount(
                login=str(account["login"]),
                account_type=str(account["type"]),
                avatar_url=str(account["avatar_url"]),
                profile_url=str(account["html_url"]),
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GitHubInstallationNotConfigured(
                "GitHub installation account could not be verified"
            ) from exc

    async def complete(self, installation_id: str, state: str) -> GitHubInstallationResult:
        if not verify_install_state(self._settings.app_secret_key, state):
            raise GitHubInstallationStateInvalid("Invalid or expired GitHub installation state")
        if not self._settings.github_app_id:
            raise GitHubInstallationNotConfigured("The server GitHub App is not configured")
        integration = await self._integration()
        if integration is None:
            integration = Integration(
                provider_type="source_control",
                provider_name="github",
                status=IntegrationStatus.CONFIGURED,
                configuration={},
            )
            self._session.add(integration)
        try:
            credential = {
                "auth_type": "github_app",
                "app_id": self._settings.github_app_id,
                "installation_id": installation_id,
                "private_key": self._private_key(),
            }
            integration.configuration = {
                "auth_type": "github_app",
                "app_slug": self._settings.github_app_slug,
            }
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
