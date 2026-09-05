import secrets
import uuid
from dataclasses import asdict
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.manage_notifications import ManageNotifications
from app.bootstrap.dependencies import get_notification_store
from app.config import Settings, get_settings
from app.db.session import SessionLocal, get_session
from app.infrastructure.persistence.notifications import SqlAlchemyNotificationStore
from app.infrastructure.telegram import TelegramService
from app.schemas import TelegramConfigure

router = APIRouter(tags=["notifications"])
webhook_router = APIRouter(tags=["telegram"])


@router.get("/notifications")
async def notifications(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    store: SqlAlchemyNotificationStore = Depends(get_notification_store),
) -> list[dict[str, object]]:
    return [asdict(item) for item in await ManageNotifications(store).list(status, limit)]


@router.get("/notifications/unread-count")
async def unread_count(
    store: SqlAlchemyNotificationStore = Depends(get_notification_store),
) -> dict[str, int]:
    return {"count": await ManageNotifications(store).unread_count()}


@router.post("/notifications/{notification_id}/{action}")
async def mark_notification(
    notification_id: uuid.UUID,
    action: str,
    store: SqlAlchemyNotificationStore = Depends(get_notification_store),
) -> dict[str, object]:
    try:
        return asdict(await ManageNotifications(store).mark(notification_id, action))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/incidents")
async def incidents(
    status: str | None = Query(default=None),
    store: SqlAlchemyNotificationStore = Depends(get_notification_store),
) -> list[dict[str, object]]:
    return await ManageNotifications(store).incidents(status)


@router.post("/incidents/{incident_id}/{action}")
async def mark_incident(
    incident_id: uuid.UUID,
    action: str,
    store: SqlAlchemyNotificationStore = Depends(get_notification_store),
) -> dict[str, object]:
    try:
        return await ManageNotifications(store).mark_incident(incident_id, action)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/notifications/telegram/connect")
async def connect_telegram(
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)
) -> dict[str, object]:
    try:
        return await TelegramService(session, settings).connect()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/notifications/telegram/configure")
async def configure_telegram(
    body: TelegramConfigure,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return await TelegramService(session, settings).configure(
            body.bot_token.get_secret_value(), body.webhook_base_url
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail="Telegram bot token could not be verified"
        ) from exc


@router.get("/notifications/telegram/status")
async def telegram_status(
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)
) -> dict[str, object]:
    return await TelegramService(session, settings).status()


@router.delete("/notifications/telegram/disconnect", status_code=204)
async def disconnect_telegram(
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)
) -> Response:
    await TelegramService(session, settings).disconnect()
    return Response(status_code=204)


async def deliver_pending() -> None:
    async with SessionLocal() as session:
        await TelegramService(session, get_settings()).deliver_pending()


@router.post("/notifications/telegram/test", status_code=202)
async def test_telegram(
    background: BackgroundTasks,
    store: SqlAlchemyNotificationStore = Depends(get_notification_store),
) -> dict[str, str]:
    from app.application.ports.notifications import RaiseIncident
    from app.domain.notifications import NotificationSeverity

    await ManageNotifications(store).raise_incident(
        RaiseIncident(
            f"telegram_test:{uuid.uuid4()}",
            "TELEGRAM_TEST",
            NotificationSeverity.ACTION_REQUIRED,
            "Telegram connection test",
            "Critical alerts from your engineering system will be delivered here.",
            action_target="/",
        )
    )
    background.add_task(deliver_pending)
    return {"status": "QUEUED"}


@webhook_router.post("/webhooks/telegram", status_code=204)
async def telegram_webhook(
    update: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    expected = await TelegramService(session, settings).webhook_secret()
    if (
        not expected
        or not x_telegram_bot_api_secret_token
        or not secrets.compare_digest(expected, x_telegram_bot_api_secret_token)
    ):
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")
    await TelegramService(session, settings).handle_update(update)
    return Response(status_code=204)
