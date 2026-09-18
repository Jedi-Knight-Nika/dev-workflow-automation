"""Bounded, resumable advisory snapshots, independent of engineering admission."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.models import AIRun
from app.analytics.domain.efficiency import task_metrics
from app.analytics.domain.forecast import VERSION, forecast
from app.analytics.infrastructure.models import TaskForecast
from app.analytics.infrastructure.persistence import SqlAnalyticsFacts
from app.engineering.infrastructure.task_models import Task
from app.observability.infrastructure.configuration import preferences

SNAPSHOT_BATCH_SIZE = 100
HISTORY_SAMPLE_SIZE = 1000


async def snapshot_forecasts(
    sessions: async_sessionmaker[AsyncSession], minimum: int, after: UUID | None = None
) -> UUID | None:
    since = datetime.now(UTC) - timedelta(days=365)
    saved = exists().where(
        TaskForecast.task_id == Task.id, TaskForecast.forecast_version == VERSION
    )
    unfinished = exists().where(
        TaskForecast.task_id == Task.id,
        TaskForecast.forecast_version == VERSION,
        TaskForecast.finalized_at.is_(None),
    )
    async with sessions() as session:
        candidates = select(Task.id).where(
            or_(
                and_(
                    Task.status.in_(["NEW", "ACTIVE"]),
                    ~saved,
                    ~exists().where(AIRun.task_id == Task.id),
                ),
                and_(Task.status.in_(["MERGED", "FAILED", "CANCELLED"]), unfinished),
            )
        )
        if after is not None:
            candidates = candidates.where(Task.id > after)
        identifiers = list(
            await session.scalars(candidates.order_by(Task.id).limit(SNAPSHOT_BATCH_SIZE))
        )
        if not identifiers:
            return None
        history_ids = list(
            await session.scalars(
                select(Task.id)
                .where(Task.status == "MERGED", Task.completed_at >= since)
                .order_by(Task.completed_at.desc(), Task.id)
                .limit(HISTORY_SAMPLE_SIZE)
            )
        )
    source = SqlAnalyticsFacts(sessions)
    facts = await source.tasks(since, task_ids=identifiers)
    history = await source.tasks(since, task_ids=history_ids)
    predictions = {
        UUID(task.id): forecast(task, history, minimum) for task in facts if not task.runs
    }
    async with sessions.begin() as session:
        current = {
            task.id: task
            for task in await session.scalars(
                select(Task).where(Task.id.in_(identifiers)).order_by(Task.id).with_for_update()
            )
        }
        snapshots = {
            row.task_id: row
            for row in await session.scalars(
                select(TaskForecast)
                .where(
                    TaskForecast.task_id.in_(identifiers), TaskForecast.forecast_version == VERSION
                )
                .with_for_update()
            )
        }
        started = set(
            await session.scalars(
                select(AIRun.task_id).where(AIRun.task_id.in_(identifiers)).distinct()
            )
        )
        additions = []
        for task in facts:
            identifier = UUID(task.id)
            latest = current.get(identifier)
            if latest is None:
                continue
            snapshot = snapshots.get(identifier)
            if (
                snapshot is None
                and identifier not in started
                and latest.status in {"NEW", "ACTIVE"}
            ):
                result = predictions.get(identifier)
                if result is not None:
                    additions.append(
                        {
                            "task_id": identifier,
                            "forecast_version": VERSION,
                            "model_kind": result["model_kind"],
                            "sample_count": result["sample_count"],
                            "confidence": result["confidence"],
                            "estimates": result["estimate"],
                        }
                    )
            elif (
                snapshot
                and snapshot.finalized_at is None
                and latest.status == task.status
                and task.status in {"MERGED", "FAILED", "CANCELLED"}
            ):
                actuals = task_metrics(task)
                if actuals["cost_complete"]:
                    snapshot.actuals = {
                        key: actuals[key]
                        for key in (
                            "cost_usd",
                            "input_tokens",
                            "output_tokens",
                            "developer_active_seconds",
                            "peak_memory_bytes",
                        )
                    }
                    snapshot.finalized_at = datetime.now(UTC)
        if additions:
            await session.execute(insert(TaskForecast).values(additions).on_conflict_do_nothing())
    structlog.get_logger().info(
        "forecast_batch_completed", candidates=len(identifiers), created=len(additions)
    )
    return identifiers[-1]


async def run_forecasts(sessions: async_sessionmaker[AsyncSession], minimum: int) -> None:
    cursor = None
    while True:
        try:
            async with asyncio.timeout(10):
                values = await preferences(sessions)
                if values.get("forecasts_enabled", True):
                    cursor = await snapshot_forecasts(
                        sessions, values.get("forecast_min_samples", minimum), cursor
                    )
        except Exception as exc:  # noqa: BLE001 -- advisory failure must remain visible without stopping engineering
            structlog.get_logger().error(
                "forecast_unavailable",
                failure_code=type(exc).__name__,
                cursor=str(cursor) if cursor else None,
            )
        await asyncio.sleep(60)
