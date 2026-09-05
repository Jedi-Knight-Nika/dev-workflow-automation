from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from app.application.ingest_webhooks import IngestWebhooks
from app.application.ports.webhook_ingestion import (
    WebhookHeadersMissing,
    WebhookIngestionWorkflow,
    WebhookPayloadInvalid,
    WebhookSignatureInvalid,
)
from app.bootstrap.dependencies import get_webhook_ingestion_workflow

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, WebhookHeadersMissing | WebhookPayloadInvalid):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=403, detail=str(exc))


@router.post("/linear", status_code=status.HTTP_200_OK)
async def linear_webhook(
    request: Request,
    workflow: WebhookIngestionWorkflow = Depends(get_webhook_ingestion_workflow),
    linear_delivery: str | None = Header(default=None),
    linear_event: str | None = Header(default=None),
    linear_signature: str | None = Header(default=None),
) -> Response:
    try:
        await IngestWebhooks(workflow).linear(
            body=await request.body(),
            delivery_id=linear_delivery,
            event_type=linear_event,
            signature=linear_signature,
        )
    except (WebhookHeadersMissing, WebhookPayloadInvalid, WebhookSignatureInvalid) as exc:
        raise _translate(exc) from exc
    return Response(status_code=200)


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    workflow: WebhookIngestionWorkflow = Depends(get_webhook_ingestion_workflow),
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
) -> Response:
    try:
        created = await IngestWebhooks(workflow).github(
            body=await request.body(),
            delivery_id=x_github_delivery,
            event_type=x_github_event,
            signature=x_hub_signature_256,
        )
    except (WebhookHeadersMissing, WebhookPayloadInvalid, WebhookSignatureInvalid) as exc:
        raise _translate(exc) from exc
    return Response(status_code=202 if created else 200)
