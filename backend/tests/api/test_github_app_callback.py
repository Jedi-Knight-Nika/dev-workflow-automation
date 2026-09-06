import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.api.control_plane import github_install_callback, github_install_url
from app.application.ports.github_installation import GitHubInstallationResult
from app.config import Settings
from app.db.models import Integration, IntegrationStatus
from app.infrastructure.github_installation import EncryptedGitHubInstallationWorkflow
from app.infrastructure.security.crypto import cipher
from app.integrations.github_auth import create_install_state


class FakeInstallationWorkflow:
    async def install_url(self) -> str:
        return "https://github.com/apps/worker/installations/new?state=signed"

    async def complete(self, installation_id: str, state: str) -> GitHubInstallationResult:
        assert installation_id == "456" and state == "signed"
        return GitHubInstallationResult("https://worker.test/integrations?github=connected", True)

    async def manage_url(self) -> str:
        return "https://github.com/settings/installations/456"


class IntegrationSession:
    def __init__(self, integration: Integration) -> None:
        self.integration = integration
        self.commits = 0

    async def scalar(self, _statement: Any) -> Integration:
        return self.integration

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_github_install_routes_delegate_to_workflow() -> None:
    workflow = FakeInstallationWorkflow()
    assert (await github_install_url(workflow=workflow))["url"].startswith("https://github.com/")  # type: ignore[arg-type]
    response = await github_install_callback("456", "signed", workflow=workflow)  # type: ignore[arg-type]
    assert response.status_code == 303
    assert response.headers["location"].endswith("github=connected")


@pytest.mark.asyncio
async def test_github_install_workflow_encrypts_installation_and_connects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "callback-test-secret-long-enough"
    credential = {
        "auth_type": "github_app",
        "app_id": "123",
        "installation_id": "",
        "private_key": "key",
    }
    integration = Integration(
        provider_type="source_control",
        provider_name="github",
        status=IntegrationStatus.CONFIGURED,
        configuration={"app_slug": "engineering-worker"},
        encrypted_credentials=cipher.encrypt(json.dumps(credential)),
    )
    session = IntegrationSession(integration)

    async def resolve_auth(_value: str) -> SimpleNamespace:
        return SimpleNamespace(token="token", installation=True)

    class Client:
        def __init__(self, _token: str, _installation: bool) -> None: ...
        async def list_repositories(self) -> list[object]:
            return []

    monkeypatch.setattr("app.infrastructure.github_installation.resolve_github_auth", resolve_auth)
    monkeypatch.setattr("app.infrastructure.github_installation.GitHubClient", Client)
    workflow = EncryptedGitHubInstallationWorkflow(
        session,
        Settings(
            app_secret_key=secret,
            github_app_slug="engineering-worker",
            github_app_id="123",
            github_app_private_key="key",
            github_app_return_url="https://worker.test/repositories",
        ),
    )  # type: ignore[arg-type]

    result = await workflow.complete("456", create_install_state(secret))

    assert result.connected and session.commits == 1
    stored = json.loads(cipher.decrypt(integration.encrypted_credentials or b""))
    assert stored["installation_id"] == "456"


@pytest.mark.asyncio
async def test_github_install_url_uses_server_owned_app_configuration() -> None:
    workflow = EncryptedGitHubInstallationWorkflow(
        IntegrationSession(Integration(provider_type="source_control", provider_name="github")),
        Settings(
            app_secret_key="callback-test-secret-long-enough",
            github_app_slug="engineering-worker",
            github_app_id="123",
            github_app_private_key="server-owned-key",
        ),
    )  # type: ignore[arg-type]

    url = await workflow.install_url()

    assert url.startswith("https://github.com/apps/engineering-worker/installations/new?")


@pytest.mark.asyncio
async def test_github_manage_url_targets_connected_installation() -> None:
    credential = {
        "auth_type": "github_app",
        "app_id": "123",
        "installation_id": "456",
        "private_key": "key",
    }
    integration = Integration(
        provider_type="source_control",
        provider_name="github",
        encrypted_credentials=cipher.encrypt(json.dumps(credential)),
    )
    workflow = EncryptedGitHubInstallationWorkflow(IntegrationSession(integration), Settings())  # type: ignore[arg-type]

    assert await workflow.manage_url() == "https://github.com/settings/installations/456"


@pytest.mark.asyncio
async def test_invalid_install_state_is_rejected_before_database_access() -> None:
    session = IntegrationSession(
        Integration(provider_type="source_control", provider_name="github")
    )
    workflow = EncryptedGitHubInstallationWorkflow(
        session, Settings(app_secret_key="callback-test-secret-long-enough")
    )  # type: ignore[arg-type]
    with pytest.raises(Exception, match="Invalid or expired"):
        await workflow.complete("456", "invalid")
    assert session.commits == 0
