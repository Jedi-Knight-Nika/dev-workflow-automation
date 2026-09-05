from app.application.ports.delivery_processing import DeliveryProcessor


class ProcessDeliveries:
    def __init__(self, processor: DeliveryProcessor) -> None:
        self._processor = processor

    async def execute(self) -> bool:
        linear = await self._processor.process_linear()
        github = await self._processor.process_github()
        return linear or github
