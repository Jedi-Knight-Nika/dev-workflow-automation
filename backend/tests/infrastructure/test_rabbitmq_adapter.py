import importlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.platform.messaging.application.ports import PublicationFailed, TaskWakeup


@pytest.fixture
def rabbit():
    return importlib.import_module("app.platform.messaging.infrastructure.rabbitmq")


def event():
    return TaskWakeup(uuid4(), uuid4(), 2, datetime.now(UTC))


def test_notification_round_trip_contains_only_identity(rabbit):
    notification = event()
    assert rabbit.decode(rabbit.encode(notification)) == notification
    assert set(json.loads(rabbit.encode(notification))) == {
        "version",
        "kind",
        "event_id",
        "task_id",
        "revision",
        "occurred_at",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"version": 2},
        {"version": True},
        {"kind": "engineering.execute"},
        {"revision": 0},
        {"revision": True},
        {"event_id": "invalid"},
        {"occurred_at": "2026-09-18T12:00:00"},
    ],
)
def test_invalid_envelopes_are_rejected(rabbit, changes):
    value = json.loads(rabbit.encode(event())) | changes
    with pytest.raises(ValueError):
        rabbit.decode(json.dumps(value).encode())


@pytest.mark.parametrize("body", [b"[]", b"null", b"{}", b"invalid", b"x" * 8193])
def test_malformed_messages_are_rejected(rabbit, body):
    with pytest.raises((ValueError, KeyError)):
        rabbit.decode(body)


async def test_publisher_requires_a_positive_confirmation(rabbit):
    exchange = AsyncMock(publish=AsyncMock(return_value=None))
    transport = rabbit.RabbitActivityTransport(exchange, AsyncMock())
    with pytest.raises(PublicationFailed):
        await transport.publish(event())
    assert exchange.publish.await_args.kwargs["mandatory"] is True
    assert exchange.publish.await_args.args[0].delivery_mode == rabbit.DeliveryMode.PERSISTENT
    exchange.publish.return_value = rabbit.Basic.Ack()
    await transport.publish(event())


async def test_publisher_sanitizes_broker_failure(rabbit):
    exchange = AsyncMock(publish=AsyncMock(side_effect=OSError("password=secret")))
    with pytest.raises(PublicationFailed, match="^OSError$"):
        await rabbit.RabbitActivityTransport(exchange, AsyncMock()).publish(event())


class Messages:
    def __init__(self, message):
        self.message = message

    @asynccontextmanager
    async def iterator(self):
        async def stream():
            yield self.message

        yield stream()


async def test_ack_follows_successful_handler(rabbit):
    order = []
    notification = event()
    message = AsyncMock(body=rabbit.encode(notification))
    message.ack.side_effect = lambda: order.append("ack")
    handler = AsyncMock(side_effect=lambda _: order.append("commit"))
    with pytest.raises(ConnectionError):
        await rabbit.RabbitActivityTransport(AsyncMock(), Messages(message)).consume(handler)
    handler.assert_awaited_once_with(notification)
    assert order == ["commit", "ack"]


async def test_handler_failure_leaves_message_unacknowledged(rabbit):
    message = AsyncMock(body=rabbit.encode(event()))
    handler = AsyncMock(side_effect=OSError("database unavailable"))
    with pytest.raises(OSError):
        await rabbit.RabbitActivityTransport(AsyncMock(), Messages(message)).consume(handler)
    message.ack.assert_not_awaited()
    message.reject.assert_not_awaited()


async def test_poison_message_is_dead_lettered_without_calling_handler(rabbit):
    message = AsyncMock(body=b"invalid")
    handler = AsyncMock()
    with pytest.raises(ConnectionError):
        await rabbit.RabbitActivityTransport(AsyncMock(), Messages(message)).consume(handler)
    message.reject.assert_awaited_once_with(requeue=False)
    handler.assert_not_awaited()


@pytest.mark.parametrize("attempt", [0, 1, 2])
async def test_handler_bug_has_durable_bounded_retries(rabbit, monkeypatch, attempt):
    monkeypatch.setattr(rabbit.asyncio, "sleep", AsyncMock())
    message = AsyncMock(body=rabbit.encode(event()), headers={rabbit.RETRY_HEADER: attempt})
    exchange = AsyncMock(publish=AsyncMock(return_value=rabbit.Basic.Ack()))
    with pytest.raises(ConnectionError):
        await rabbit.RabbitActivityTransport(exchange, Messages(message)).consume(
            AsyncMock(side_effect=RuntimeError("private data must not be logged"))
        )
    if attempt == 2:
        message.reject.assert_awaited_once_with(requeue=False)
        message.ack.assert_not_awaited()
        exchange.publish.assert_not_awaited()
    else:
        published = exchange.publish.await_args.args[0]
        assert published.headers[rabbit.RETRY_HEADER] == attempt + 1
        message.ack.assert_awaited_once()
        message.reject.assert_not_awaited()


async def test_unconfirmed_retry_does_not_ack_original(rabbit, monkeypatch):
    monkeypatch.setattr(rabbit.asyncio, "sleep", AsyncMock())
    message = AsyncMock(body=rabbit.encode(event()), headers={})
    exchange = AsyncMock(publish=AsyncMock(return_value=None))
    with pytest.raises(PublicationFailed):
        await rabbit.RabbitActivityTransport(exchange, Messages(message)).consume(
            AsyncMock(side_effect=RuntimeError())
        )
    message.ack.assert_not_awaited()
    message.reject.assert_not_awaited()


async def test_cancelled_handler_never_acks_or_republishes(rabbit):
    import asyncio

    message = AsyncMock(body=rabbit.encode(event()), headers={})
    exchange = AsyncMock()
    with pytest.raises(asyncio.CancelledError):
        await rabbit.RabbitActivityTransport(exchange, Messages(message)).consume(
            AsyncMock(side_effect=asyncio.CancelledError())
        )
    exchange.publish.assert_not_awaited()
    message.ack.assert_not_awaited()
