import json

import httpx
import pytest

from app.supervisor.infrastructure.transport import request_decision


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,error",
    [
        (200, b'{"usage": {}}', None),
        (200, b"[]", TypeError),
        (200, b"x" * 64001, ValueError),
        (503, b"unavailable", httpx.HTTPStatusError),
    ],
)
async def test_transport_is_bounded_and_does_not_retry(monkeypatch, status, body, error):
    calls = []

    def respond(request):
        calls.append(request)
        assert json.loads(request.content) == {"store": False}
        assert request.headers["Authorization"] == "Bearer test-only"
        return httpx.Response(status, content=body)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(respond)),
    )
    if error:
        with pytest.raises(error):
            await request_decision({"store": False}, "test-only")
    else:
        assert await request_decision({"store": False}, "test-only") == {"usage": {}}
    assert len(calls) == 1
