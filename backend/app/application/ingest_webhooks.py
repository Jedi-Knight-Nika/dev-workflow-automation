from app.application.ports.webhook_ingestion import WebhookIngestionWorkflow


class IngestWebhooks:
    def __init__(self, workflow: WebhookIngestionWorkflow) -> None:
        self._workflow = workflow

    async def github(self, **values: object) -> bool:
        return await self._workflow.ingest_github(**values)  # type: ignore[arg-type]

    async def linear(self, **values: object) -> bool:
        return await self._workflow.ingest_linear(**values)  # type: ignore[arg-type]
