"""Warn about Docker host limits without silently changing execution authority."""

import httpx
import structlog

from app.agent_runtime.infrastructure.container import RUNNER_CPUS, RUNNER_MEMORY_BYTES
from app.platform.configuration.settings import Settings


async def check_host_capacity(settings: Settings) -> None:
    log = structlog.get_logger()
    slots = settings.global_developer_slots + settings.validation_slots
    try:
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=str(settings.docker_socket)),
            base_url="http://docker",
            timeout=5,
        ) as client:
            response = await client.get("/info")
            response.raise_for_status()
            info = response.json()
        memory, cpus = int(info["MemTotal"]), int(info["NCPU"])
        if slots * RUNNER_MEMORY_BYTES + 2 * 1024**3 > memory or slots * RUNNER_CPUS > cpus:
            log.warning(
                "runner_capacity_exceeds_host",
                slots=slots,
                maximum_memory_bytes=slots * RUNNER_MEMORY_BYTES,
                docker_memory_bytes=memory,
                maximum_cpus=slots * RUNNER_CPUS,
                docker_cpus=cpus,
            )
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("runner_capacity_unknown", error_type=type(exc).__name__)
