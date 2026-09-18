"""Activity notification process; database reconciliation remains the recovery path."""

import asyncio
from time import monotonic

import structlog
from aio_pika.exceptions import AMQPException
from sqlalchemy.exc import SQLAlchemyError

from app.bootstrap.activity import activity_sessions, create_activity_projector
from app.platform.configuration.settings import Settings
from app.platform.messaging.application.dispatch import DispatchOutbox, DispatchResult
from app.platform.messaging.application.ports import PublicationFailed, TaskWakeup
from app.platform.messaging.infrastructure.outbox import SqlEventOutbox
from app.platform.messaging.infrastructure.rabbitmq import activity_transport


async def run_messaging(settings: Settings) -> None:
    if not settings.rabbitmq_url:
        raise ValueError("RABBITMQ_URL is required for RabbitMQ transport")

    log = structlog.get_logger()
    outbox = SqlEventOutbox(activity_sessions())
    projector = create_activity_projector()

    async def project(_event: TaskWakeup) -> None:
        if settings.activity_enabled:
            await projector.execute(maintain=False)

    async def dispatch(dispatcher: DispatchOutbox) -> None:
        last_report = 0.0
        counts = dict.fromkeys(DispatchResult, 0)
        while True:
            result = await dispatcher.execute()
            counts[result] += 1
            if result == DispatchResult.RETRY:
                raise PublicationFailed("Reconnect after unconfirmed publication")
            if monotonic() - last_report >= 60:
                pending, age = await outbox.backlog()
                log.info(
                    "notification_transport_status",
                    pending=pending,
                    oldest_seconds=round(age, 1),
                    **counts,
                )
                await outbox.prune()
                counts = dict.fromkeys(DispatchResult, 0)
                last_report = monotonic()
            if result != DispatchResult.PUBLISHED:
                await asyncio.sleep(1)

    while True:
        try:
            async with activity_transport(settings.rabbitmq_url) as transport:
                log.info("notification_transport_connected")
                async with asyncio.TaskGroup() as workers:
                    workers.create_task(dispatch(DispatchOutbox(outbox, transport)))
                    workers.create_task(transport.consume(project))
        except* (
            PublicationFailed,
            AMQPException,
            SQLAlchemyError,
            OSError,
            TimeoutError,
        ) as errors:
            log.warning(
                "notification_transport_delayed",
                error_types=sorted({type(error).__name__ for error in errors.exceptions}),
            )
            await asyncio.sleep(5)
