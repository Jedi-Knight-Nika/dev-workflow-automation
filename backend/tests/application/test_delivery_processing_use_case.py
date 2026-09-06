import pytest

from app.application.process_deliveries import ProcessDeliveries


class FakeDeliveryProcessor:
    def __init__(self, linear: bool, github: bool) -> None:
        self.linear = linear
        self.github = github
        self.calls: list[str] = []

    async def process_linear(self) -> bool:
        self.calls.append("linear")
        return self.linear

    async def process_github(self) -> bool:
        self.calls.append("github")
        return self.github


@pytest.mark.asyncio
async def test_delivery_processing_runs_both_durable_queues() -> None:
    processor = FakeDeliveryProcessor(True, False)
    assert await ProcessDeliveries(processor).execute()
    assert processor.calls == ["linear", "github"]
