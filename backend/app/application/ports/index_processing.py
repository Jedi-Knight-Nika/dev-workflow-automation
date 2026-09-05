from typing import Protocol


class IndexProcessor(Protocol):
    async def process_next(self) -> bool: ...
