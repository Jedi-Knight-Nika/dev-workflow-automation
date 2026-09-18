"""Optional, resource-limited projector process. No scheduler, tools or provider credentials."""

import asyncio
import signal

import structlog

from app.bootstrap.activity import create_activity_projector
from app.platform.configuration.settings import get_settings
from app.platform.persistence import registry as _registry  # noqa: F401
from app.platform.telemetry.logging import configure_logging


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    stopped = asyncio.Event()
    for name in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(name, stopped.set)
    if not settings.activity_enabled:
        await stopped.wait()
        return
    projector = create_activity_projector()
    while not stopped.is_set():
        try:
            await projector.execute()
        except Exception as exc:  # noqa: BLE001 -- optional process boundary; only the error class is logged
            structlog.get_logger().warning(
                "activity_projection_delayed", error_type=type(exc).__name__
            )
        try:
            await asyncio.wait_for(stopped.wait(), timeout=settings.activity_poll_seconds)
        except TimeoutError:
            pass


if __name__ == "__main__":
    asyncio.run(run())
