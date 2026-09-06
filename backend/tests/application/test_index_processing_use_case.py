import pytest

from app.application.process_indexes import ProcessIndexes


class FakeIndexProcessor:
    def __init__(self) -> None:
        self.calls = 0

    async def process_next(self) -> bool:
        self.calls += 1
        return True


@pytest.mark.asyncio
async def test_index_processing_delegates_to_processor_port() -> None:
    processor = FakeIndexProcessor()
    assert await ProcessIndexes(processor).execute()
    assert processor.calls == 1
