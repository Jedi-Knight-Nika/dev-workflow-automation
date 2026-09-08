"""Optional background snapshots; never scheduled as an engineering job."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.models import AIRun
from app.analytics.domain.efficiency import task_metrics
from app.analytics.domain.forecast import VERSION, forecast
from app.analytics.infrastructure.models import TaskForecast
from app.analytics.infrastructure.persistence import SqlAnalyticsFacts
from app.observability.infrastructure.configuration import preferences


async def snapshot_forecasts(sessions: async_sessionmaker[AsyncSession], minimum: int) -> None:
    facts = await SqlAnalyticsFacts(sessions).tasks(datetime.now(UTC) - timedelta(days=365))
    for task in facts:
        identifier = UUID(task.id)
        async with sessions.begin() as session:
            saved = await session.scalar(
                select(TaskForecast).where(
                    TaskForecast.task_id == identifier, TaskForecast.forecast_version == VERSION
                )
            )
            if saved is None and not task.runs and task.status in {"NEW", "ACTIVE"}:
                result = forecast(task, facts, minimum)
                # Recheck current receipts immediately before storing; predictions
                # use only outcomes before the target's creation regardless.
                if not await session.scalar(select(exists().where(AIRun.task_id == identifier))):
                    await session.execute(
                        insert(TaskForecast)
                        .values(
                            task_id=identifier,
                            forecast_version=VERSION,
                            model_kind=result["model_kind"],
                            sample_count=result["sample_count"],
                            confidence=result["confidence"],
                            estimates=result["estimate"],
                        )
                        .on_conflict_do_nothing()
                    )
            elif (
                saved
                and saved.finalized_at is None
                and task.status in {"MERGED", "FAILED", "CANCELLED"}
            ):
                actuals = task_metrics(task)
                if actuals["cost_complete"]:
                    saved.actuals = {
                        key: actuals[key]
                        for key in (
                            "cost_usd",
                            "input_tokens",
                            "output_tokens",
                            "developer_active_seconds",
                            "peak_memory_bytes",
                        )
                    }
                    saved.finalized_at = datetime.now(UTC)


async def run_forecasts(sessions: async_sessionmaker[AsyncSession], minimum: int) -> None:
    while True:
        try:
            async with asyncio.timeout(10):
                values = await preferences(sessions)
                if values.get("forecasts_enabled", True):
                    await snapshot_forecasts(sessions, values.get("forecast_min_samples", minimum))
        except Exception as exc:  # noqa: BLE001 - advisory work never breaks a task
            structlog.get_logger().warning("forecast_unavailable", failure_code=type(exc).__name__)
        await asyncio.sleep(60)
