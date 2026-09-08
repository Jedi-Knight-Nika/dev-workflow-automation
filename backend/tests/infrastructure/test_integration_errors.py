from unittest.mock import AsyncMock

import httpx
import pytest

from app.platform.integrations.application.ports.integration_discovery import (
    IntegrationNotConfigured,
)
from app.platform.integrations.infrastructure.discovery import EncryptedIntegrationDiscoveryWorkflow
from app.platform.integrations.infrastructure.errors import connection_error
from app.platform.integrations.infrastructure.management import (
    EncryptedIntegrationManagementWorkflow,
)
from app.platform.integrations.models import Integration
from app.platform.scheduling.states import IntegrationStatus
from app.platform.security.crypto import cipher


def rejected(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.trello.com/1/members/me/boards?token=secret")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        "Raw failure containing secret", request=request, response=response
    )


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "Trello rejected"),
        (403, "denied access"),
        (429, "rate limiting"),
        (503, "temporarily unavailable"),
    ],
)
def test_provider_failures_are_actionable_without_urls_or_secrets(
    status: int, expected: str
) -> None:
    message = connection_error("trello", rejected(status))
    assert expected in message
    assert "secret" not in message and "https://" not in message


@pytest.mark.asyncio
async def test_failed_verification_persists_clear_error_and_retains_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = cipher.encrypt('{"api_key":"example-key","token":"example-token"}')
    row = Integration(
        provider_name="trello",
        provider_type="task_management",
        status=IntegrationStatus.CONFIGURED,
        configuration={},
        encrypted_credentials=credentials,
    )
    session = AsyncMock()
    session.scalar.return_value = row
    monkeypatch.setattr(
        "app.intake.infrastructure.trello_client.TrelloClient.list_boards",
        AsyncMock(side_effect=rejected(401)),
    )
    result = await EncryptedIntegrationManagementWorkflow(session).verify("trello")
    assert result.status == "ERROR" and "Trello rejected" in result.last_error
    assert row.encrypted_credentials == credentials
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,args", [("trello_boards", ()), ("trello_lists", ("board",))])
async def test_discovery_converts_upstream_unauthorized_into_controlled_error(
    method: str, args: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = EncryptedIntegrationDiscoveryWorkflow(AsyncMock())
    monkeypatch.setattr(
        store, "_credential", AsyncMock(return_value='{"api_key":"key","token":"token"}')
    )
    monkeypatch.setattr(
        "app.intake.infrastructure.trello_client.TrelloClient._get",
        AsyncMock(side_effect=rejected(401)),
    )
    with pytest.raises(IntegrationNotConfigured, match="Trello rejected"):
        await getattr(store, method)(*args)
