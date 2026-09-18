"""One demand-driven watermark poller per process; durable stores own replay."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog


class StreamSignal:
    def __init__(self, watermark: Callable[[], Awaitable[int]], interval: float = 1) -> None:
        self.watermark = watermark
        self.interval = interval
        self.listeners: set[asyncio.Event] = set()
        self.task: asyncio.Task[None] | None = None

    async def _poll(self) -> None:
        previous = None
        while True:
            try:
                current = await self.watermark()
                if current != previous:
                    for listener in self.listeners:
                        listener.set()
                    previous = current
            except Exception as exc:  # noqa: BLE001 -- keep reconnectable streams alive during storage outages
                structlog.get_logger().error("stream_poll_failed", error_type=type(exc).__name__)
                for listener in self.listeners:
                    listener.set()
            await asyncio.sleep(self.interval)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Event]:
        listener = asyncio.Event()
        self.listeners.add(listener)
        if self.task is None:
            self.task = asyncio.create_task(self._poll())
        try:
            yield listener
        finally:
            self.listeners.remove(listener)
            if not self.listeners and self.task is not None:
                task, self.task = self.task, None
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def wait_for_change(listener: asyncio.Event, timeout: float) -> bool:
    try:
        await asyncio.wait_for(listener.wait(), timeout)
    except TimeoutError:
        return False
    listener.clear()
    return True
