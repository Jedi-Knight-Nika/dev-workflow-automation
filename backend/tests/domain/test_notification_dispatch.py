import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.platform.messaging.application.dispatch import DispatchOutbox, DispatchResult
from app.platform.messaging.application.ports import OutboxClaim, PublicationFailed, TaskWakeup


def claim():
    return OutboxClaim(TaskWakeup(uuid4(), uuid4(), 1, datetime.now(UTC)), uuid4())


async def test_empty_outbox_does_not_publish():
    outbox = AsyncMock(claim=AsyncMock(return_value=None))
    publisher = AsyncMock()
    assert await DispatchOutbox(outbox, publisher).execute() == DispatchResult.EMPTY
    publisher.publish.assert_not_awaited()


async def test_publish_happens_before_marking_delivery():
    leased = claim()
    order = []
    outbox = AsyncMock(claim=AsyncMock(return_value=leased))
    publisher = AsyncMock()
    publisher.publish.side_effect = lambda _: order.append("publish")
    outbox.published.side_effect = lambda _: order.append("commit")
    assert await DispatchOutbox(outbox, publisher).execute() == DispatchResult.PUBLISHED
    assert order == ["publish", "commit"]
    publisher.publish.assert_awaited_once_with(leased.event)
    outbox.published.assert_awaited_once_with(leased)


async def test_failure_retains_event_without_persisting_exception_secrets():
    leased = claim()
    outbox = AsyncMock(claim=AsyncMock(return_value=leased))
    publisher = AsyncMock(publish=AsyncMock(side_effect=PublicationFailed("password=secret")))
    assert await DispatchOutbox(outbox, publisher).execute() == DispatchResult.RETRY
    outbox.published.assert_not_awaited()
    outbox.retry.assert_awaited_once_with(leased, "PublicationFailed")


async def test_timeout_retains_event():
    outbox = AsyncMock(claim=AsyncMock(return_value=claim()))

    async def wait(_event):
        await asyncio.Event().wait()

    publisher = AsyncMock(publish=AsyncMock(side_effect=wait))
    result = await DispatchOutbox(outbox, publisher, timeout_seconds=0.001).execute()
    assert result == DispatchResult.RETRY
    outbox.published.assert_not_awaited()


async def test_cancellation_leaves_lease_for_recovery():
    outbox = AsyncMock(claim=AsyncMock(return_value=claim()))
    publisher = AsyncMock(publish=AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await DispatchOutbox(outbox, publisher).execute()
    outbox.retry.assert_not_awaited()
    outbox.published.assert_not_awaited()


async def test_failed_delivery_commit_does_not_lose_event():
    outbox = AsyncMock(claim=AsyncMock(return_value=claim()))
    outbox.published.side_effect = OSError("database unavailable")
    publisher = AsyncMock()
    with pytest.raises(OSError):
        await DispatchOutbox(outbox, publisher).execute()
    publisher.publish.assert_awaited_once()
    outbox.retry.assert_not_awaited()
