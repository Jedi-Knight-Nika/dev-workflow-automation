from typing import cast

import pytest
from fastapi import Request

from app.api.events import sse_messages


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_sse_survives_repeated_heartbeats() -> None:
    messages = sse_messages(cast(Request, ConnectedRequest()), heartbeat_seconds=0.001)
    try:
        assert await anext(messages) == ": keepalive\n\n"
        assert await anext(messages) == ": keepalive\n\n"
    finally:
        await messages.aclose()
