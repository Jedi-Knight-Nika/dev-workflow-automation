import asyncio
from collections.abc import Mapping
from typing import Any

import httpx

TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


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
