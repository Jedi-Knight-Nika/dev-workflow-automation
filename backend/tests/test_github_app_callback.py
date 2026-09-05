import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.control_plane import github_install_callback, github_install_url
from app.config import Settings
from app.db.models import Integration, IntegrationStatus
from app.integrations.github_auth import create_install_state
from app.services.crypto import cipher


class IntegrationSession:
    def __init__(self, integration: Integration) -> None:
        self.integration = integration
        self.commits = 0

    async def scalar(self, _statement: Any) -> Integration:
        return self.integration

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_github_install_url_uses_saved_app_slug() -> None:
    integration = Integration(
        provider_type="source_control",
        provider_name="github",
        configuration={"auth_type": "github_app", "app_slug": "engineering-worker"},
        encrypted_credentials=b"configured",
    )

    result = await github_install_url(
        session=IntegrationSession(integration),  # type: ignore[arg-type]
        settings=Settings(app_secret_key="callback-test-secret-long-enough"),
    )

    assert result["url"].startswith(
        "https://github.com/apps/engineering-worker/installations/new?state="
    )


@pytest.mark.asyncio
async def test_github_install_url_rejects_invalid_saved_slug() -> None:
    integration = Integration(
        provider_type="source_control",
        provider_name="github",
        configuration={"auth_type": "github_app", "app_slug": "../wrong"},
        encrypted_credentials=b"configured",
    )

    with pytest.raises(HTTPException, match="slug is invalid") as raised:
        await github_install_url(
            session=IntegrationSession(integration),  # type: ignore[arg-type]
            settings=Settings(app_secret_key="callback-test-secret-long-enough"),
        )

    assert raised.value.status_code == 422


@pytest.mark.asyncio
async def test_github_install_callback_encrypts_installation_and_connects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "callback-test-secret-long-enough"
    credential = {
        "auth_type": "github_app",
        "app_id": "123",
        "installation_id": "",
        "private_key": "private-key",
    }
    integration = Integration(
        provider_type="source_control",
        provider_name="github",
        status=IntegrationStatus.CONFIGURED,
        configuration={"auth_type": "github_app", "app_slug": "engineering-worker"},
        encrypted_credentials=cipher.encrypt(json.dumps(credential)),
    )
    session = IntegrationSession(integration)
    verified_credentials: list[str] = []

    async def resolve_auth(value: str) -> SimpleNamespace:
        verified_credentials.append(value)
        return SimpleNamespace(token="installation-token", installation=True)

    class Client:
        def __init__(self, token: str, installation: bool) -> None:
            assert token == "installation-token"
            assert installation is True

        async def list_repositories(self) -> list[dict[str, str]]:
            return []

    monkeypatch.setattr("app.api.control_plane.resolve_github_auth", resolve_auth)
    monkeypatch.setattr("app.api.control_plane.GitHubClient", Client)

    response = await github_install_callback(
        installation_id="456",
        state=create_install_state(secret),
        session=session,  # type: ignore[arg-type]
        settings=Settings(
            app_secret_key=secret,
            github_app_return_url="https://worker.example.com/integrations",
        ),
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "https://worker.example.com/integrations?github=connected"
    )
    assert session.commits == 1
    assert integration.status == IntegrationStatus.CONNECTED
    stored = json.loads(cipher.decrypt(integration.encrypted_credentials or b""))
    assert stored["installation_id"] == "456"
    assert json.loads(verified_credentials[0])["installation_id"] == "456"


@pytest.mark.asyncio
async def test_github_install_callback_rejects_invalid_state_before_database_access() -> None:
    integration = Integration(provider_type="source_control", provider_name="github")
    session = IntegrationSession(integration)

    with pytest.raises(HTTPException, match="Invalid or expired") as raised:
        await github_install_callback(
            installation_id="456",
            state="invalid",
            session=session,  # type: ignore[arg-type]
            settings=Settings(app_secret_key="callback-test-secret-long-enough"),
        )

    assert raised.value.status_code == 400
    assert session.commits == 0
