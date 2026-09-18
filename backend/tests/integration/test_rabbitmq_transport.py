import asyncio
import importlib
import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.platform.messaging.application.ports import PublicationFailed, TaskWakeup


@pytest.fixture
def broker():
    url = os.getenv("TEST_RABBITMQ_URL")
    if not url:
        pytest.skip("Set TEST_RABBITMQ_URL to an isolated RabbitMQ test vhost")
    pytest.importorskip("aio_pika")
    return url, importlib.import_module("app.platform.messaging.infrastructure.rabbitmq")


async def test_confirmed_delivery_redelivery_and_poison_routing(broker):
    url, rabbit = broker
    event = TaskWakeup(uuid4(), uuid4(), 1, datetime.now(UTC))
    async with rabbit.activity_transport(url) as transport:
        await transport.queue.purge()
        await transport.publish(event)
        message = await transport.queue.get(timeout=5)
        assert rabbit.decode(message.body) == event
        await message.nack(requeue=True)
    async with rabbit.activity_transport(url) as transport:
        message = await transport.queue.get(timeout=5)
        assert rabbit.decode(message.body) == event and message.redelivered
        await message.ack()
        handler = AsyncMock()
        consumer = asyncio.create_task(transport.consume(handler))
        try:
            await transport.exchange.publish(
                rabbit.Message(b"invalid"), routing_key=rabbit.ROUTING_KEY, mandatory=True
            )
            dead = await transport.queue.channel.get_queue("aew.activity.dead")
            async with asyncio.timeout(5):
                while True:
                    poison = await dead.get(fail=False)
                    if poison:
                        assert poison.body == b"invalid"
                        await poison.ack()
                        break
                    await asyncio.sleep(0.05)
            handler.assert_not_awaited()
        finally:
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)


async def test_unroutable_publication_is_not_reported_as_success(broker):
    url, rabbit = broker
    async with rabbit.activity_transport(url) as transport:
        await transport.queue.unbind(transport.exchange, routing_key=rabbit.ROUTING_KEY)
        try:
            with pytest.raises(PublicationFailed):
                await transport.publish(TaskWakeup(uuid4(), uuid4(), 1, datetime.now(UTC)))
        finally:
            await transport.queue.bind(transport.exchange, routing_key=rabbit.ROUTING_KEY)


async def test_handler_failure_is_redelivered_after_connection_closes(broker):
    url, rabbit = broker
    event = TaskWakeup(uuid4(), uuid4(), 1, datetime.now(UTC))
    async with rabbit.activity_transport(url) as transport:
        await transport.queue.purge()
        await transport.publish(event)
        async with asyncio.timeout(5):
            with pytest.raises(OSError):
                await transport.consume(AsyncMock(side_effect=OSError("Database unavailable")))
    async with rabbit.activity_transport(url) as transport:
        message = await transport.queue.get(timeout=5)
        assert message.redelivered and rabbit.decode(message.body) == event
        await message.ack()


async def test_transactional_outbox_to_projection_is_duplicate_safe(
    broker, postgres_session_factory, monkeypatch
):
    from sqlalchemy import delete, func, select

    from app.activity.infrastructure.projector import ActivityProjector
    from app.engineering.domain.lifecycle import Action
    from app.engineering.infrastructure.lifecycle import record_transition
    from app.platform.configuration.settings import get_settings
    from app.platform.messaging.application.dispatch import DispatchOutbox, DispatchResult
    from app.platform.messaging.infrastructure.outbox import SqlEventOutbox
    from app.platform.persistence.registry import ActivityEvent, NotificationOutbox, Task

    url, rabbit = broker
    factory = postgres_session_factory
    task_id = uuid4()
    monkeypatch.setattr(get_settings(), "event_transport", "rabbitmq")
    async with factory.begin() as session:
        session.add(Task(id=task_id, title="Broker projection round trip"))
        await session.flush()
        await record_transition(session, task_id, Action.CANCEL, expected_version=1, actor="test")
    try:
        projector = ActivityProjector(factory, batch_size=1000)
        async with rabbit.activity_transport(url) as transport:
            await transport.queue.purge()
            assert (
                await DispatchOutbox(SqlEventOutbox(factory), transport).execute()
                == DispatchResult.PUBLISHED
            )
            message = await transport.queue.get(timeout=5)
            event = rabbit.decode(message.body)
            assert event.task_id == task_id
            await projector.project()
            await message.ack()
            async with factory() as session:
                query = (
                    select(func.count())
                    .select_from(ActivityEvent)
                    .where(ActivityEvent.task_id == task_id)
                )
                before = await session.scalar(query)
                assert before > 0
            await transport.publish(event)
            duplicate = await transport.queue.get(timeout=5)
            assert rabbit.decode(duplicate.body) == event
            await projector.project()
            await duplicate.ack()
            async with factory() as session:
                assert await session.scalar(query) == before
                row = await session.get(NotificationOutbox, event.event_id)
                assert row.published_at is not None
    finally:
        async with factory.begin() as session:
            await session.execute(delete(ActivityEvent).where(ActivityEvent.task_id == task_id))
            await session.execute(
                delete(NotificationOutbox).where(NotificationOutbox.task_id == task_id)
            )
            await session.execute(delete(Task).where(Task.id == task_id))
