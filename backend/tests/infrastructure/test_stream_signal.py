import asyncio
from unittest.mock import AsyncMock

from app.platform.scheduling.stream_signal import StreamSignal, wait_for_change


async def test_connections_share_one_poller_and_last_disconnect_stops_it():
    watermark = AsyncMock(return_value=1)
    signal = StreamSignal(watermark, interval=0.005)
    async with signal.subscribe() as first:
        running = signal.task
        async with signal.subscribe() as second:
            assert signal.task is running
            assert await wait_for_change(first, 1)
            assert await wait_for_change(second, 1)
            initial = watermark.await_count
            assert not await wait_for_change(first, 0.015)
            assert watermark.await_count > initial
            watermark.return_value = 2
            assert await wait_for_change(first, 1)
            assert await wait_for_change(second, 1)
        assert signal.task is running
    assert signal.task is None
    assert running.done()
    assert not signal.listeners


async def test_slow_subscriber_coalesces_signals_without_an_unbounded_buffer():
    watermark = AsyncMock(side_effect=range(100))
    signal = StreamSignal(watermark, interval=0.001)
    async with signal.subscribe() as listener:
        await asyncio.sleep(0.01)
        assert listener.is_set()
        assert len(signal.listeners) == 1
        assert await wait_for_change(listener, 1)
