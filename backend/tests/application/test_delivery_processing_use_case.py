from unittest.mock import AsyncMock

import pytest

from app.intake.application.process_deliveries import ProcessDeliveries


@pytest.mark.parametrize("productive", [None, "linear", "status", "github", "text", "review"])
async def test_processing_preserves_order_without_short_circuiting(productive):
    order = []

    def step(name):
        async def run():
            order.append(name)
            return name == productive

        return AsyncMock(side_effect=run)

    processor = AsyncMock(
        process_linear=step("linear"),
        process_github=step("github"),
        process_review_text=step("text"),
    )
    processing = ProcessDeliveries(
        processor, sync_status=step("status"), recheck_review=step("review")
    )
    assert await processing.execute() is (productive is not None)
    assert order == ["linear", "status", "github", "text", "review"]


async def test_failure_propagates_without_running_later_steps():
    processor = AsyncMock()
    status = AsyncMock(side_effect=OSError("unavailable"))
    review = AsyncMock()
    with pytest.raises(OSError):
        await ProcessDeliveries(processor, sync_status=status, recheck_review=review).execute()
    processor.process_linear.assert_awaited_once()
    processor.process_github.assert_not_awaited()
    processor.process_review_text.assert_not_awaited()
    review.assert_not_awaited()
