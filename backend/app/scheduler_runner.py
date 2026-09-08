import asyncio
import signal

import structlog

from app.bootstrap.scheduler import create_scheduler
from app.platform.configuration.settings import get_settings
from app.platform.telemetry.logging import configure_logging


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = structlog.get_logger()
    if not settings.scheduler_enabled:
        # An explicitly disabled Compose worker must not dispatch anything. Stay
        # idle until stopped so restart policies cannot turn this into a spin loop.
        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        for name in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(name, stopped.set)
        log.info("worker_service_disabled")
        await stopped.wait()
        return
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    scheduler = create_scheduler(settings)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stopped.set)
    await scheduler.start()
    try:
        log.info("worker_service_started")
        await stopped.wait()
    finally:
        await scheduler.stop()
    log.info("worker_service_stopped")


if __name__ == "__main__":
    asyncio.run(run())
