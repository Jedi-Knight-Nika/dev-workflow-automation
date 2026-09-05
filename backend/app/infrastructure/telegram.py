import hashlib
import html
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import (
    Integration,
    IntegrationStatus,
    Notification,
    NotificationDelivery,
    TelegramConnection,
    TelegramConnectionToken,
    TelegramUpdate,
)
from app.infrastructure.security.crypto import cipher


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class TelegramService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def configure(
        self, bot_token: str, webhook_base_url: str | None = None
    ) -> dict[str, object]:
        token = bot_token.strip()
        if not token:
            raise ValueError("Telegram bot token cannot be empty")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            response.raise_for_status()
            result = response.json().get("result", {})
        username = result.get("username")
        if not isinstance(username, str) or not username:
            raise ValueError("Telegram did not return a bot username")
        base_url = (webhook_base_url or "").strip().rstrip("/")
        if base_url and not base_url.startswith("https://"):
            raise ValueError("Telegram webhook URL must use HTTPS")
        webhook_configured = False
        if base_url:
            secret_token = hashlib.sha256(
                f"{self._settings.app_secret_key}:{token}".encode()
            ).hexdigest()
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/setWebhook",
                    json={
                        "url": f"{base_url}/webhooks/telegram",
                        "secret_token": secret_token,
                        "allowed_updates": ["message", "callback_query"],
                    },
                )
                response.raise_for_status()
            webhook_configured = True
        integration = await self._integration()
        if integration is None:
            integration = Integration(provider_type="notification", provider_name="telegram")
            self._session.add(integration)
        integration.encrypted_credentials = cipher.encrypt(token)
        integration.configuration = {
            "bot_username": username,
            "webhook_base_url": base_url,
            "webhook_configured": webhook_configured,
        }
        integration.status = IntegrationStatus.CONNECTED
        integration.last_error = None
        await self._session.commit()
        return await self.status()

    async def connect(self, user_id: str = "local-user") -> dict[str, object]:
        integration = await self._integration()
        if integration is None or integration.encrypted_credentials is None:
            raise RuntimeError("Telegram bot is not configured")
        username = str(integration.configuration.get("bot_username", ""))
        raw = secrets.token_urlsafe(24)
        expires = datetime.now(UTC) + timedelta(minutes=10)
        self._session.add(
            TelegramConnectionToken(user_id=user_id, token_hash=token_hash(raw), expires_at=expires)
        )
        await self._session.commit()
        return {
            "bot_username": username,
            "connect_url": f"https://t.me/{username}?start={raw}",
            "expires_at": expires,
        }

    async def status(self, user_id: str = "local-user") -> dict[str, object]:
        connection = await self._connection(user_id)
        integration = await self._integration()
        return {
            "configured": bool(integration and integration.encrypted_credentials),
            "connected": bool(connection and connection.enabled),
            "username": connection.telegram_username if connection else None,
            "last_delivery_at": connection.last_delivery_at if connection else None,
            "last_delivery_error": connection.last_delivery_error if connection else None,
            "webhook_configured": bool(
                integration and integration.configuration.get("webhook_configured")
            ),
        }

    async def disconnect(self, user_id: str = "local-user") -> None:
        connection = await self._connection(user_id)
        if connection:
            connection.enabled = False
            await self._session.commit()

    async def handle_update(self, update: dict[str, Any]) -> None:
        update_id = update.get("update_id")
        processed = (
            await self._session.scalar(
                select(TelegramUpdate.update_id).where(TelegramUpdate.update_id == update_id)
            )
            if isinstance(update_id, int)
            else None
        )
        if not isinstance(update_id, int) or processed is not None:
            return
        self._session.add(TelegramUpdate(update_id=update_id))
        message = update.get("message")
        callback = update.get("callback_query")
        if isinstance(message, dict):
            await self._handle_start(message)
        elif isinstance(callback, dict):
            await self._handle_callback(callback)
        await self._session.commit()

    async def deliver_pending(self, limit: int = 20) -> None:
        integration = await self._integration()
        if integration is None or integration.encrypted_credentials is None:
            return
        bot_token = cipher.decrypt(integration.encrypted_credentials)
        deliveries = (
            await self._session.scalars(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.channel == "TELEGRAM",
                    NotificationDelivery.state.in_(("PENDING", "RETRY")),
                    NotificationDelivery.attempt_count < 4,
                )
                .order_by(NotificationDelivery.created_at)
                .limit(limit)
            )
        ).all()
        for delivery in deliveries:
            await self._deliver(delivery, bot_token)

    async def webhook_secret(self) -> str | None:
        integration = await self._integration()
        if integration is None or integration.encrypted_credentials is None:
            return None
        token = cipher.decrypt(integration.encrypted_credentials)
        return hashlib.sha256(f"{self._settings.app_secret_key}:{token}".encode()).hexdigest()

    async def _handle_start(self, message: dict[str, Any]) -> None:
        text = message.get("text")
        chat, sender = message.get("chat"), message.get("from")
        if not isinstance(text, str) or not text.startswith("/start "):
            return
        if not isinstance(chat, dict) or not isinstance(sender, dict):
            return
        record = await self._session.scalar(
            select(TelegramConnectionToken).where(
                TelegramConnectionToken.token_hash == token_hash(text.split(maxsplit=1)[1]),
                TelegramConnectionToken.used_at.is_(None),
                TelegramConnectionToken.expires_at > datetime.now(UTC),
            )
        )
        if record is None:
            return
        connection = await self._connection(record.user_id)
        values = {
            "telegram_user_id": str(sender.get("id")),
            "telegram_chat_id": str(chat.get("id")),
            "telegram_username": sender.get("username"),
            "enabled": True,
            "connected_at": datetime.now(UTC),
        }
        if connection:
            for key, value in values.items():
                setattr(connection, key, value)
        else:
            self._session.add(TelegramConnection(user_id=record.user_id, **values))
        record.used_at = datetime.now(UTC)

    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        data = callback.get("data")
        if not isinstance(data, str) or not data.startswith("ack:"):
            return
        try:
            notification_id = uuid.UUID(data.removeprefix("ack:"))
        except ValueError:
            return
        notification = await self._session.get(Notification, notification_id)
        message = callback.get("message")
        chat = message.get("chat") if isinstance(message, dict) else None
        chat_id = str(chat.get("id")) if isinstance(chat, dict) else ""
        connection = await self._connection(notification.user_id) if notification else None
        if (
            notification
            and connection
            and connection.telegram_chat_id == chat_id
            and notification.status != "RESOLVED"
        ):
            notification.status = "ACKNOWLEDGED"
            notification.acknowledged_at = datetime.now(UTC)

    async def _deliver(self, delivery: NotificationDelivery, bot_token: str) -> None:
        notification = await self._session.get(Notification, delivery.notification_id)
        if notification is None:
            delivery.state = "FAILED"
            await self._session.commit()
            return
        delivery.attempt_count += 1
        delivery.last_attempt_at = datetime.now(UTC)
        prefix = "🚨 CRITICAL" if notification.severity == "CRITICAL" else "⚠️ ACTION REQUIRED"
        text = f"<b>{prefix}</b>\n\n<b>{html.escape(notification.title)}</b>\n{html.escape(notification.message[:1500])}"
        buttons: list[list[dict[str, str]]] = []
        if notification.action_target:
            target = notification.action_target
            if target.startswith("/"):
                target = self._settings.application_base_url.rstrip("/") + target
            buttons.append([{"text": "Open Dashboard", "url": target}])
        buttons.append([{"text": "Acknowledge", "callback_data": f"ack:{notification.id}"}])
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": delivery.recipient_ref,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": {"inline_keyboard": buttons},
                    },
                )
                response.raise_for_status()
                payload = response.json()
            delivery.state = "DELIVERED"
            delivery.delivered_at = datetime.now(UTC)
            delivery.external_message_id = str(payload.get("result", {}).get("message_id", ""))
            delivery.failure_code = delivery.failure_message = None
        except (httpx.HTTPError, ValueError) as exc:
            delivery.state = "RETRY" if delivery.attempt_count < 4 else "FAILED"
            delivery.failure_code = type(exc).__name__
            delivery.failure_message = str(exc)[:1000]
        await self._session.commit()

    async def _connection(self, user_id: str) -> TelegramConnection | None:
        connection: TelegramConnection | None = await self._session.scalar(
            select(TelegramConnection).where(TelegramConnection.user_id == user_id)
        )
        return connection

    async def _integration(self) -> Integration | None:
        integration: Integration | None = await self._session.scalar(
            select(Integration).where(Integration.provider_name == "telegram")
        )
        return integration
