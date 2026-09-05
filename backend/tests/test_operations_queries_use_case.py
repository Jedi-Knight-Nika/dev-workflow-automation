from datetime import UTC, datetime

import pytest

from app.application.operations import QueryOperations
from app.application.ports.operations_queries import ActivityView, WebhookHealthView


class FakeOperationsQueries:
    async def activity(self) -> ActivityView:
        return ActivityView(None, [])

    async def webhook_health(self) -> list[WebhookHealthView]:
        now = datetime.now(UTC)
        return [WebhookHealthView("github", 2, 1, now, None, "delivery failed")]


@pytest.mark.asyncio
async def test_operations_reads_delegate_through_query_port() -> None:
    operations = QueryOperations(FakeOperationsQueries())

    assert await operations.activity() == ActivityView(None, [])
    health = await operations.webhook_health()
    assert health[0].provider == "github"
    assert health[0].pending == 2
    assert health[0].failed == 1
