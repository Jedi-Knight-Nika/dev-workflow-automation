import asyncio
from collections.abc import Callable, Mapping
from typing import Any

import httpx

TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class IntegrationHttpPool:
    """Own one connection-pooled client for external integration adapters."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._factory: Callable[..., httpx.AsyncClient] | None = None
        self._lock = asyncio.Lock()

    async def client(self) -> httpx.AsyncClient:
        factory = httpx.AsyncClient
        async with self._lock:
            if self._client is None or self._client.is_closed or self._factory is not factory:
                if self._client is not None and not self._client.is_closed:
                    await self._client.aclose()
                self._client = factory(timeout=30, follow_redirects=True)
                self._factory = factory
            return self._client

    async def request(
        self,
        method: str,
        url: str,
        *,
        retry: bool = True,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        client = await self.client()
        if retry:
            return await request_with_retry(
                client, method, url, headers=headers, params=params, json=json
            )
        return await client.request(method, url, headers=headers, params=params, json=json)

    async def aclose(self) -> None:
        async with self._lock:
            if self._client is not None and not self._client.is_closed:
                await self._client.aclose()
            self._client = None
            self._factory = None


integration_http_pool = IntegrationHttpPool()


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                parsed_retry_after = float(str(retry_after))
                return float(min(30.0, max(0.0, parsed_retry_after)))
            except ValueError:
                pass
    return float(min(8.0, 0.5 * (2**attempt)))


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    attempts: int = 3,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    json: Any = None,
) -> httpx.Response:
    """Retry only transient transport/status failures with bounded backoff."""
    if attempts < 1:
        raise ValueError("Retry attempts must be at least one")
    last_error: httpx.RequestError | None = None
    response: httpx.Response | None = None
    for attempt in range(attempts):
        response = None
        try:
            response = await client.request(method, url, headers=headers, params=params, json=json)
            if response.status_code not in TRANSIENT_STATUS_CODES:
                return response
        except httpx.RequestError as exc:
            last_error = exc
        if attempt + 1 < attempts:
            await asyncio.sleep(_retry_delay(response, attempt))
    if last_error is not None and response is None:
        raise last_error
    assert response is not None
    return response
