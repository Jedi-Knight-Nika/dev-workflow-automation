"""Bounded Supervisor HTTP transport; no task state, SQL, or retry policy."""

import asyncio
import json
from typing import Any

import httpx


async def request_decision(payload: dict[str, Any], key: str) -> dict[str, Any]:
    async with (
        asyncio.timeout(45),
        httpx.AsyncClient(timeout=40, trust_env=False) as client,
        client.stream(
            "POST",
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        ) as response,
    ):
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > 64000:
                raise ValueError("Supervisor response exceeds bound")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise TypeError("Supervisor response must be an object")
    return data
