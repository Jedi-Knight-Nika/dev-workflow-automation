import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.agent_runtime.infrastructure.egress_proxy import destination
from app.intake.application.ports.webhook_ingestion import WebhookPayloadInvalid
from app.intake.infrastructure.webhook_ingestion import SqlAlchemyWebhookIngestionWorkflow
from app.interfaces.http.routes.webhooks import bounded_body


@pytest.mark.parametrize("host", ["api.openai.com", "api.anthropic.com", "github.com"])
def test_provider_gateway_accepts_only_explicit_tls_destinations(host: str) -> None:
    assert destination(f"CONNECT {host}:443 HTTP/1.1\r\n\r\n".encode()) == host


@pytest.mark.parametrize(
    "target",
    [
        "127.0.0.1:443",
        "api.openai.com.evil.test:443",
        "github.com:80",
        "postgres:5432",
        "api.github.com:443",
        "user@github.com:443",
        "github.com.:443",
    ],
)
def test_proxy_denies_unapproved_routes(target: str) -> None:
    with pytest.raises(ValueError):
        destination(f"CONNECT {target} HTTP/1.1\r\n\r\n".encode())


@pytest.mark.parametrize("body", [b"[]", b"null", b"1", b"\xff", b"x" * 1_000_001])
def test_all_provider_ingestion_requires_bounded_json_object(body: bytes) -> None:
    with pytest.raises(WebhookPayloadInvalid):
        SqlAlchemyWebhookIngestionWorkflow._payload(body)


@pytest.mark.asyncio
async def test_body_limit_applies_to_streamed_payload_not_only_content_length() -> None:
    chunks = iter([b"x" * 600_000, b"x" * 600_000])

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    request = Request({"type": "http", "headers": []}, receive=receive)
    with pytest.raises(HTTPException) as error:
        await bounded_body(request)
    assert error.value.status_code == 413


def test_valid_webhook_payload_is_not_reformatted() -> None:
    assert SqlAlchemyWebhookIngestionWorkflow._payload(
        json.dumps({"action": "created"}).encode()
    ) == {"action": "created"}
