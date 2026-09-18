import asyncio
import signal

from app.bootstrap.messaging import run_messaging
from app.platform.configuration.settings import get_settings
from app.platform.persistence import registry as _registry  # noqa: F401
from app.platform.telemetry.logging import configure_logging


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    stopped = asyncio.Event()
    for name in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(name, stopped.set)
    worker = asyncio.create_task(run_messaging(settings))
    stop = asyncio.create_task(stopped.wait())
    try:
        finished, _ = await asyncio.wait({worker, stop}, return_when=asyncio.FIRST_COMPLETED)
        if worker in finished:
            worker.result()
    finally:
        worker.cancel()
        stop.cancel()
        await asyncio.gather(worker, stop, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(run())
