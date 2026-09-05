import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.webhook_ingestion import (
    WebhookHeadersMissing,
    WebhookPayloadInvalid,
    WebhookSignatureInvalid,
)
from app.config import Settings
from app.db.models import WebhookDelivery
from app.integrations.github import verify_signature
from app.integrations.linear import verify_linear_signature


class SqlAlchemyWebhookIngestionWorkflow:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session, self._settings = session, settings

    async def _commit(self) -> bool:
        try:
            await self._session.commit()
            return True
        except IntegrityError:
            await self._session.rollback()
            return False

    async def ingest_github(
        self, *, body: bytes, delivery_id: str | None, event_type: str | None, signature: str | None
    ) -> bool:
        if not delivery_id or not event_type:
            raise WebhookHeadersMissing("Missing GitHub delivery headers")
        if not verify_signature(body, self._settings.github_webhook_secret, signature):
            raise WebhookSignatureInvalid("Invalid GitHub webhook signature")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WebhookPayloadInvalid("Invalid JSON payload") from exc
        repository = payload.get("repository") or {}
        self._session.add(
            WebhookDelivery(
                provider="github",
                delivery_id=delivery_id,
                event_type=event_type,
                action=payload.get("action"),
                repository_external_id=str(repository.get("id")) if repository.get("id") else None,
                payload=payload,
            )
        )
        return await self._commit()

    async def ingest_linear(
        self, *, body: bytes, delivery_id: str | None, event_type: str | None, signature: str | None
    ) -> bool:
        if not delivery_id or not event_type:
            raise WebhookHeadersMissing("Missing Linear delivery headers")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WebhookPayloadInvalid("Invalid JSON payload") from exc
        timestamp = payload.get("webhookTimestamp")
        if not verify_linear_signature(
            body,
            self._settings.linear_webhook_secret,
            signature,
            timestamp if isinstance(timestamp, int) else None,
        ):
            raise WebhookSignatureInvalid("Invalid or stale Linear webhook signature")
        self._session.add(
            WebhookDelivery(
                provider="linear",
                delivery_id=delivery_id,
                event_type=event_type,
                action=payload.get("action"),
                payload=payload,
            )
        )
        return await self._commit()
