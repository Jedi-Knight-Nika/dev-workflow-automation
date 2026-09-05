from app.application.ports.operations_queries import (
    ActivityView,
    OperationsQueries,
    WebhookHealthView,
)


class QueryOperations:
    def __init__(self, queries: OperationsQueries) -> None:
        self._queries = queries

    async def activity(self) -> ActivityView:
        return await self._queries.activity()

    async def webhook_health(self) -> list[WebhookHealthView]:
        return await self._queries.webhook_health()
