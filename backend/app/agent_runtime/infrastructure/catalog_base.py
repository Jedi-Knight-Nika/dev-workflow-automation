import asyncio
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ProviderModel:
    id: str
    display_name: str


class ProviderRequestError(RuntimeError):
    """Safe, typed provider failure suitable for worker-to-scheduler transport."""

    def __init__(self, code: str, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(f"{code}: provider request failed with HTTP {status_code}")


class AIProvider(ABC):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    def client(self) -> httpx.AsyncClient:
        """Reuse connections across authenticated model discovery requests."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: int = 30,
        headers: Mapping[str, str] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        """Retry only transient transport, throttling, and provider failures."""
        delays = (0.5, 1.0, 2.0)
        for attempt in range(len(delays) + 1):
            try:
                response = await self.client().request(
                    method,
                    url,
                    timeout=timeout_seconds,
                    headers=headers,
                    json=json,
                )
                if response.is_success:
                    return response
                error = self.provider_error(response)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    raise error
                if attempt >= len(delays):
                    raise error
                retry_after = (
                    response.headers.get("retry-after") if response.status_code == 429 else None
                )
                try:
                    delay = min(float(retry_after), 10.0) if retry_after else delays[attempt]
                except ValueError:
                    delay = delays[attempt]
                await asyncio.sleep(delay)
            except httpx.TransportError:
                if attempt >= len(delays):
                    raise RuntimeError("PROVIDER_UNAVAILABLE: provider transport failed") from None
                await asyncio.sleep(delays[attempt])
        raise RuntimeError("Provider request retry loop exited unexpectedly")

    @staticmethod
    def provider_error(response: httpx.Response) -> ProviderRequestError:
        body = response.text.upper()
        status = response.status_code
        if status in {401, 403}:
            code = "PROVIDER_AUTH_ERROR"
        elif status == 404 or any(
            marker in body
            for marker in ("MODEL_NOT_FOUND", "MODEL NOT FOUND", "UNKNOWN MODEL", "DEPRECATED")
        ):
            code = "MODEL_UNAVAILABLE"
        elif any(
            marker in body for marker in ("CONTEXT_LENGTH", "CONTEXT LIMIT", "TOO MANY TOKENS")
        ):
            code = "MODEL_CONTEXT_LIMIT"
        elif status == 429:
            code = "PROVIDER_RATE_LIMIT"
        elif status in {500, 502, 503, 504}:
            code = "PROVIDER_UNAVAILABLE"
        else:
            code = "MODEL_POLICY_ERROR"
        return ProviderRequestError(code, status)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @abstractmethod
    async def list_models(self) -> list[ProviderModel]: ...
