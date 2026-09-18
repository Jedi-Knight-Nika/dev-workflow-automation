import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.bootstrap import messaging
from app.platform.configuration.settings import Settings
from app.platform.messaging.application.ports import PublicationFailed


@pytest.mark.parametrize("activity_enabled", [True, False])
async def test_messaging_starts_without_a_transport_switch(monkeypatch, activity_enabled):
    assert "event_transport" not in Settings.model_fields
    monkeypatch.setenv("EVENT_TRANSPORT", "postgres")
    connected = asyncio.Event()
    projector = AsyncMock()
    outbox = AsyncMock()
    outbox.claim.return_value = None
    outbox.backlog.return_value = (0, 0)
    transport = AsyncMock()

    async def consume(handle):
        await handle(None)
        connected.set()
        await asyncio.Event().wait()

    transport.consume.side_effect = consume

    @asynccontextmanager
    async def connection(url):
        assert url == "amqp://test"
        yield transport

    monkeypatch.setattr(messaging, "activity_transport", connection)
    monkeypatch.setattr(messaging, "activity_sessions", Mock())
    monkeypatch.setattr(messaging, "SqlEventOutbox", Mock(return_value=outbox))
    monkeypatch.setattr(messaging, "create_activity_projector", Mock(return_value=projector))
    running = asyncio.create_task(
        messaging.run_messaging(
            Settings(_env_file=None, rabbitmq_url="amqp://test", activity_enabled=activity_enabled)
        )
    )
    try:
        async with asyncio.timeout(2):
            await connected.wait()
        assert projector.execute.await_count == int(activity_enabled)
        if activity_enabled:
            projector.execute.assert_awaited_once_with(maintain=False)
        outbox.claim.assert_awaited()
        assert not running.done()
    finally:
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running


async def test_messaging_requires_explicit_connection_configuration():
    with pytest.raises(ValueError, match="RABBITMQ_URL"):
        await messaging.run_messaging(Settings(_env_file=None, rabbitmq_url=""))


async def test_broker_outage_reconnects_without_switching_transport(monkeypatch):
    reconnected = asyncio.Event()
    attempts = 0
    delay = AsyncMock()

    @asynccontextmanager
    async def connection(url):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("Broker unavailable")
        reconnected.set()
        await asyncio.Event().wait()
        yield AsyncMock()

    monkeypatch.setattr(messaging, "activity_transport", connection)
    monkeypatch.setattr(messaging.asyncio, "sleep", delay)
    monkeypatch.setattr(messaging, "activity_sessions", Mock())
    monkeypatch.setattr(messaging, "SqlEventOutbox", Mock())
    monkeypatch.setattr(messaging, "create_activity_projector", Mock())
    running = asyncio.create_task(
        messaging.run_messaging(Settings(_env_file=None, rabbitmq_url="amqp://test"))
    )
    try:
        async with asyncio.timeout(2):
            await reconnected.wait()
        assert attempts == 2
        delay.assert_awaited_once_with(5)
    finally:
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running


@pytest.mark.parametrize("failure", [TypeError("Invalid internal state"), ValueError("Bug")])
async def test_programming_errors_are_not_silently_retried(monkeypatch, failure):
    outbox = AsyncMock()
    outbox.claim.side_effect = failure
    transport = AsyncMock()
    closed = asyncio.Event()
    cancelled = asyncio.Event()

    async def consume(handle):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    transport.consume.side_effect = consume

    @asynccontextmanager
    async def connection(url):
        try:
            yield transport
        finally:
            closed.set()

    monkeypatch.setattr(messaging, "activity_transport", connection)
    monkeypatch.setattr(messaging, "activity_sessions", Mock())
    monkeypatch.setattr(messaging, "SqlEventOutbox", Mock(return_value=outbox))
    monkeypatch.setattr(messaging, "create_activity_projector", Mock())
    async with asyncio.timeout(0.5):
        with pytest.raises(ExceptionGroup) as errors:
            await messaging.run_messaging(Settings(_env_file=None, rabbitmq_url="amqp://test"))
    assert errors.value.exceptions == (failure,)
    assert closed.is_set() and cancelled.is_set()
    outbox.claim.assert_awaited_once_with()


@pytest.mark.parametrize(
    "failure",
    [
        PublicationFailed("password=private"),
        SQLAlchemyError("password=private"),
        ExceptionGroup("private", [OSError("private"), TimeoutError("private")]),
        ExceptionGroup("outer", [ExceptionGroup("inner", [OSError("private")])]),
    ],
)
async def test_transient_failures_retry_without_logging_details(monkeypatch, failure):
    retrying = asyncio.Event()
    log = Mock()

    @asynccontextmanager
    async def connection(url):
        raise failure
        yield

    async def pause(seconds):
        assert seconds == 5
        retrying.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(messaging, "activity_transport", connection)
    monkeypatch.setattr(messaging.asyncio, "sleep", pause)
    monkeypatch.setattr(messaging.structlog, "get_logger", Mock(return_value=log))
    monkeypatch.setattr(messaging, "activity_sessions", Mock())
    monkeypatch.setattr(messaging, "SqlEventOutbox", Mock())
    monkeypatch.setattr(messaging, "create_activity_projector", Mock())
    running = asyncio.create_task(
        messaging.run_messaging(Settings(_env_file=None, rabbitmq_url="amqp://test"))
    )
    try:
        async with asyncio.timeout(1):
            await retrying.wait()
        log.warning.assert_called_once()
        assert log.warning.call_args.args == ("notification_transport_delayed",)
        assert "private" not in str(log.warning.call_args)
    finally:
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
