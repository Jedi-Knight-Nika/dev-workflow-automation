import asyncio
import signal

import structlog

from app.bootstrap.scheduler import create_scheduler
from app.config import get_settings
from app.logging import configure_logging


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = structlog.get_logger()
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    scheduler = create_scheduler(settings)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stopped.set)
    await scheduler.start()
    log.info("worker_service_started")
    await stopped.wait()
    await scheduler.stop()
    log.info("worker_service_stopped")


if __name__ == "__main__":
    asyncio.run(run())
