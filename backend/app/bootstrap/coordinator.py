"""Independent coordination worker; no paid polling when there are no events."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic

import structlog

from app.coordinator.application.ports import CoordinationAdministration
from app.coordinator.infrastructure.actions import ActionExecutor
from app.coordinator.infrastructure.model import MeteredDecisionModel
from app.coordinator.infrastructure.processor import CoordinatorProcessor
from app.platform.configuration.settings import get_settings
from app.platform.integrations.infrastructure.conversations import ProviderConversations
from app.platform.persistence.session import SessionLocal


@asynccontextmanager
async def coordinator_controller() -> AsyncIterator[None]:
    settings = get_settings()
    if settings.coordinator_mode == "off" or not settings.scheduler_enabled:
        yield
        return
    gateway = ProviderConversations(SessionLocal)
    processor = CoordinatorProcessor(
        SessionLocal, settings, MeteredDecisionModel(SessionLocal, settings), gateway
    )
    executor = ActionExecutor(SessionLocal, gateway)

    async def run(*, decisions: bool) -> None:
        recovered = 0.0
        while True:
            try:
                if not decisions and monotonic() - recovered > 30:
                    await processor.recover()
                    await executor.recover()
                    recovered = monotonic()
                if decisions:
                    worked = await processor.process_one()
                else:
                    acted = await executor.execute_one()
                    delivered = await executor.deliver_one()
                    reconciled = await executor.reconcile_one()
                    worked = acted or delivered or reconciled
                if not worked:
                    await asyncio.sleep(1)
            except Exception as exc:  # noqa: BLE001 -- persist a sanitized failure at the worker/effect boundary
                structlog.get_logger().warning(
                    "coordinator_iteration_failed", error_type=type(exc).__name__
                )
                await asyncio.sleep(1)

    workers = [
        asyncio.create_task(run(decisions=True), name="coordinator-decisions"),
        asyncio.create_task(run(decisions=False), name="coordinator-effects"),
    ]
    try:
        yield
    finally:
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


def coordination_administration() -> "CoordinationAdministration":
    from app.coordinator.infrastructure.administration import (
        CoordinationAdministration as SqlAdministration,
    )

    return SqlAdministration(SessionLocal, get_settings())
