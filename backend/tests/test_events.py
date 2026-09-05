import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request

from app.api.events import sse_messages


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_sse_survives_repeated_heartbeats(monkeypatch: pytest.MonkeyPatch) -> None:
    async def empty_events(_: int) -> list[object]:
        return []

    async def zero_cursor() -> int:
        return 0

    monkeypatch.setattr("app.api.events.events_after", empty_events)
    monkeypatch.setattr("app.api.events.latest_event_id", zero_cursor)
    messages = sse_messages(
        cast(Request, ConnectedRequest()), heartbeat_seconds=0.001, poll_seconds=0.001
    )
    try:
        assert await anext(messages) == ": keepalive\n\n"
        assert await anext(messages) == ": keepalive\n\n"
    finally:
        await messages.aclose()


@pytest.mark.asyncio
async def test_sse_replays_durable_event_with_id(monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = uuid.uuid4()

    async def durable_events(_: int) -> list[object]:
        return [SimpleNamespace(id=12, task_id=task_id, event_type="JOB_SUCCEEDED")]

    async def latest_cursor() -> int:
        return 12

    monkeypatch.setattr("app.api.events.events_after", durable_events)
    monkeypatch.setattr("app.api.events.latest_event_id", latest_cursor)
    messages = sse_messages(cast(Request, ConnectedRequest()))
    try:
        message = await anext(messages)
        assert message.startswith("id: 12\nevent: update\n")
        assert '"event_type": "JOB_SUCCEEDED"' in message
    finally:
        await messages.aclose()
