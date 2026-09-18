"""Optional, resource-limited projector process. No scheduler, tools or provider credentials."""

import asyncio
import signal

import structlog

from app.activity.infrastructure.files import collect_files
from app.activity.infrastructure.projector import ActivityProjector
from app.activity.infrastructure.retention import expire_file_details
from app.bootstrap.activity import activity_sessions
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
    projector = ActivityProjector(activity_sessions())
    while not stopped.is_set():
        try:
            await projector.project()
            if settings.activity_collect_files:
                await collect_files(activity_sessions(), settings.workspace_root)
            await expire_file_details(activity_sessions(), settings.activity_file_retention_days)
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
