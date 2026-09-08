from typing import Protocol


class WebhookHeadersMissing(Exception):
    pass


class WebhookPayloadInvalid(Exception):
    pass


class WebhookSignatureInvalid(Exception):
    pass


class WebhookIngestionWorkflow(Protocol):
    async def ingest_slack(
        self, *, body: bytes, timestamp: str | None, signature: str | None
    ) -> dict[str, str]: ...
    async def ingest_trello(self, *, body: bytes, signature: str | None) -> bool: ...
    async def ingest_github(
        self, *, body: bytes, delivery_id: str | None, event_type: str | None, signature: str | None
    ) -> bool: ...
    async def ingest_linear(
        self, *, body: bytes, delivery_id: str | None, event_type: str | None, signature: str | None
    ) -> bool: ...
