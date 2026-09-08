import base64
import hashlib
import hmac
import json
import time
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.webhook_ingestion import (
    WebhookHeadersMissing,
    WebhookPayloadInvalid,
    WebhookSignatureInvalid,
)
from app.config import Settings
from app.db.models import WebhookDelivery
from app.intake.infrastructure.slack import verify_slack_signature
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

    @staticmethod
    def _payload(body: bytes) -> dict[str, Any]:
        if len(body) > 1_000_000:
            raise WebhookPayloadInvalid("Webhook body exceeds 1 MB")
        try:
            result = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise WebhookPayloadInvalid("Invalid JSON payload") from exc
        if not isinstance(result, dict):
            raise WebhookPayloadInvalid("Webhook payload must be an object")
        return result

    async def ingest_slack(
        self, *, body: bytes, timestamp: str | None, signature: str | None
    ) -> dict[str, str]:
        if not verify_slack_signature(
            body=body,
            timestamp=timestamp or "",
            signature=signature or "",
            secret=self._settings.slack_signing_secret,
            now=int(time.time()),
        ):
            raise WebhookSignatureInvalid("Invalid or stale Slack signature")
        payload = self._payload(body)
        if payload.get("type") == "url_verification":
            return {"challenge": str(payload.get("challenge") or "")[:500]}
        event_id = payload.get("event_id")
        if not isinstance(event_id, str) or not event_id or len(event_id) > 255:
            raise WebhookPayloadInvalid("Slack event ID is required")
        self._session.add(
            WebhookDelivery(
                provider="slack", delivery_id=event_id, event_type="event_callback", payload=payload
            )
        )
        await self._commit()
        return {"status": "accepted"}

    async def ingest_trello(self, *, body: bytes, signature: str | None) -> bool:
        secret, callback = (
            self._settings.trello_webhook_secret,
            self._settings.trello_webhook_callback_url,
        )
        expected = base64.b64encode(
            hmac.new(secret.encode(), body + callback.encode(), hashlib.sha1).digest()
        ).decode()
        if (
            not secret
            or not callback
            or not signature
            or not hmac.compare_digest(expected, signature)
        ):
            raise WebhookSignatureInvalid("Invalid Trello signature")
        payload = self._payload(body)
        action = payload.get("action") or {}
        if not isinstance(action, dict):
            raise WebhookPayloadInvalid("Trello action must be an object")
        event_id = str(action.get("id") or "")
        if not event_id or len(event_id) > 255:
            raise WebhookPayloadInvalid("Trello action ID is required")
        self._session.add(
            WebhookDelivery(
                provider="trello",
                delivery_id=event_id,
                event_type=str(action.get("type") or "unknown"),
                payload=payload,
            )
        )
        return await self._commit()

    async def ingest_github(
        self, *, body: bytes, delivery_id: str | None, event_type: str | None, signature: str | None
    ) -> bool:
        if not delivery_id or not event_type:
            raise WebhookHeadersMissing("Missing GitHub delivery headers")
        if not verify_signature(body, self._settings.github_webhook_secret, signature):
            raise WebhookSignatureInvalid("Invalid GitHub webhook signature")
        payload = self._payload(body)
        repository = payload.get("repository") or {}
        if not isinstance(repository, dict):
            raise WebhookPayloadInvalid("GitHub repository must be an object")
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
        payload = self._payload(body)
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
