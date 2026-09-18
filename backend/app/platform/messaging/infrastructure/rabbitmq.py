"""Optional AMQP adapter. No task execution, database access or provider credentials."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from aio_pika import DeliveryMode, ExchangeType, Message, connect
from aio_pika.abc import AbstractExchange, AbstractQueue
from aio_pika.exceptions import CONNECTION_EXCEPTIONS
from pamqp.commands import Basic

from app.platform.messaging.application.ports import PublicationFailed, TaskWakeup

ROUTING_KEY = "engineering.lifecycle.changed"


def encode(event: TaskWakeup) -> bytes:
    return json.dumps(
        {
            "version": 1,
            "kind": ROUTING_KEY,
            "event_id": str(event.event_id),
            "task_id": str(event.task_id),
            "revision": event.revision,
            "occurred_at": event.occurred_at.isoformat(),
        }
    ).encode()


def decode(body: bytes) -> TaskWakeup:
    if len(body) > 8192:
        raise ValueError("Notification exceeds size limit")
    value = json.loads(body)
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value["version"] != 1
    ):
        raise ValueError("Unsupported notification version")
    if value.get("kind") != ROUTING_KEY:
        raise ValueError("Unsupported notification kind")
    if type(value.get("revision")) is not int or value["revision"] < 1:
        raise ValueError("Invalid lifecycle revision")
    occurred_at = datetime.fromisoformat(value["occurred_at"])
    if occurred_at.tzinfo is None:
        raise ValueError("Notification time requires a timezone")
    return TaskWakeup(
        UUID(value["event_id"]), UUID(value["task_id"]), value["revision"], occurred_at
    )


class RabbitActivityTransport:
    def __init__(self, exchange: AbstractExchange, queue: AbstractQueue) -> None:
        self.exchange, self.queue = exchange, queue

    async def publish(self, event: TaskWakeup) -> None:
        try:
            await self._publish(event)
        except CONNECTION_EXCEPTIONS as exc:
            raise PublicationFailed(type(exc).__name__) from exc

    async def _publish(self, event: TaskWakeup) -> None:
        confirmation = await self.exchange.publish(
            Message(
                body=encode(event),
                content_type="application/json",
                delivery_mode=DeliveryMode.PERSISTENT,
                message_id=str(event.event_id),
                type=ROUTING_KEY,
            ),
            routing_key=ROUTING_KEY,
            mandatory=True,
            timeout=5,
        )
        if not isinstance(confirmation, Basic.Ack):
            raise PublicationFailed("Notification was not confirmed")

    async def consume(self, handle: Callable[[TaskWakeup], Awaitable[None]]) -> None:
        async with self.queue.iterator() as messages:
            async for message in messages:
                try:
                    event = decode(message.body)
                except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
                    await message.reject(requeue=False)
                    continue
                await handle(event)
                await message.ack()
        raise ConnectionError("Activity consumer stopped")


@asynccontextmanager
async def activity_transport(url: str) -> AsyncIterator[RabbitActivityTransport]:
    connection = await connect(url, timeout=5)
    async with connection:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        await channel.set_qos(prefetch_count=1)
        exchange = await channel.declare_exchange("aew.events", ExchangeType.TOPIC, durable=True)
        dead = await channel.declare_exchange("aew.dead", ExchangeType.TOPIC, durable=True)
        dead_queue = await channel.declare_queue("aew.activity.dead", durable=True)
        await dead_queue.bind(dead, routing_key=ROUTING_KEY)
        queue = await channel.declare_queue(
            "aew.activity",
            durable=True,
            arguments={"x-dead-letter-exchange": "aew.dead"},
        )
        await queue.bind(exchange, routing_key=ROUTING_KEY)
        yield RabbitActivityTransport(exchange, queue)
