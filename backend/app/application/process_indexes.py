from app.application.ports.index_processing import IndexProcessor


class ProcessIndexes:
    def __init__(self, processor: IndexProcessor) -> None:
        self._processor = processor

    async def execute(self) -> bool:
        return await self._processor.process_next()
