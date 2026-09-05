import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import WebhookDelivery
from app.db.session import get_session
from app.integrations.github import verify_signature
from app.integrations.linear import verify_linear_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/linear", status_code=status.HTTP_200_OK)
async def linear_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    linear_delivery: str | None = Header(default=None),
    linear_event: str | None = Header(default=None),
    linear_signature: str | None = Header(default=None),
) -> Response:
    if not linear_delivery or not linear_event:
        raise HTTPException(status_code=400, detail="Missing Linear delivery headers")
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    timestamp = payload.get("webhookTimestamp")
    if not verify_linear_signature(
        body,
        get_settings().linear_webhook_secret,
        linear_signature,
        timestamp if isinstance(timestamp, int) else None,
    ):
        raise HTTPException(status_code=403, detail="Invalid or stale Linear webhook signature")
    session.add(
        WebhookDelivery(
            provider="linear",
            delivery_id=linear_delivery,
            event_type=linear_event,
            action=payload.get("action"),
            payload=payload,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
    return Response(status_code=status.HTTP_200_OK)


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
) -> Response:
    if not x_github_delivery or not x_github_event:
        raise HTTPException(status_code=400, detail="Missing GitHub delivery headers")
    body = await request.body()
    if not verify_signature(body, get_settings().github_webhook_secret, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid GitHub webhook signature")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    repository = payload.get("repository") or {}
    session.add(
        WebhookDelivery(
            provider="github",
            delivery_id=x_github_delivery,
            event_type=x_github_event,
            action=payload.get("action"),
            repository_external_id=(str(repository.get("id")) if repository.get("id") else None),
            payload=payload,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return Response(status_code=status.HTTP_200_OK)
    return Response(status_code=status.HTTP_202_ACCEPTED)
