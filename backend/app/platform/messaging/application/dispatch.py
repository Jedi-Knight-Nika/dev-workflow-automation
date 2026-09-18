import asyncio
from enum import StrEnum

from app.platform.messaging.application.ports import EventOutbox, EventPublisher, PublicationFailed


class DispatchResult(StrEnum):
    EMPTY = "empty"
    PUBLISHED = "published"
    RETRY = "retry"


class DispatchOutbox:
    def __init__(
        self, outbox: EventOutbox, publisher: EventPublisher, *, timeout_seconds: float = 10
    ) -> None:
        self.outbox, self.publisher = outbox, publisher
        self.timeout_seconds = timeout_seconds

    async def execute(self) -> DispatchResult:
        claim = await self.outbox.claim()
        if claim is None:
            return DispatchResult.EMPTY
        try:
            async with asyncio.timeout(self.timeout_seconds):
                await self.publisher.publish(claim.event)
        except (PublicationFailed, TimeoutError) as exc:
            await self.outbox.retry(claim, type(exc).__name__)
            return DispatchResult.RETRY
        await self.outbox.published(claim)
        return DispatchResult.PUBLISHED
