from collections.abc import Awaitable, Callable

from app.intake.application.ports.delivery_processing import DeliveryProcessor


class ProcessDeliveries:
    def __init__(
        self,
        processor: DeliveryProcessor,
        *,
        sync_status: Callable[[], Awaitable[bool]],
        recheck_review: Callable[[], Awaitable[bool]],
    ) -> None:
        self._processor = processor
        self._sync_status, self._recheck_review = sync_status, recheck_review

    async def execute(self) -> bool:
        linear = await self._processor.process_linear()
        synced = await self._sync_status()
        github = await self._processor.process_github()
        interpreted = await self._processor.process_review_text()
        checked = await self._recheck_review()
        return linear or synced or github or interpreted or checked
