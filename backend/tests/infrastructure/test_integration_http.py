import httpx
import pytest

from app.integrations.http import IntegrationHttpPool, request_with_retry


@pytest.mark.asyncio
async def test_pool_reuses_client_and_closes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    created = 0
    original = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        nonlocal created
        created += 1
        return original(transport=httpx.MockTransport(lambda request: httpx.Response(200)))

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    pool = IntegrationHttpPool()

    first = await pool.client()
    second = await pool.client()

    assert first is second
    assert created == 1
    await pool.aclose()
    assert first.is_closed


@pytest.mark.asyncio
async def test_transient_status_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = iter((503, 200))
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses), request=request)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("app.integrations.http.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await request_with_retry(client, "GET", "https://example.test")

    assert response.status_code == 200
    assert len(sleeps) == 1


@pytest.mark.asyncio
async def test_retry_after_header_controls_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = iter((429, 200))
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        headers = {"retry-after": "3"} if status == 429 else {}
        return httpx.Response(status, headers=headers, request=request)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("app.integrations.http.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await request_with_retry(client, "GET", "https://example.test")

    assert response.status_code == 200
    assert sleeps == [3.0]


@pytest.mark.asyncio
async def test_non_transient_failure_is_not_retried() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await request_with_retry(client, "GET", "https://example.test")

    assert response.status_code == 401
    assert calls == 1
