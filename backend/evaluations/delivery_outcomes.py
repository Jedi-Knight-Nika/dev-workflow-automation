"""Read actual Developer delivery outcomes for an explicitly selected comparison cohort.

Use the existing engine to execute the same cases with each chosen profile, then
export their task UUIDs here. No new inference, task mutation, or provider effect.
These observations are not a randomized quality comparison or proof of correctness.
"""

import argparse
import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.platform.persistence.registry  # noqa: F401
from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.requirements import current_requirement
from app.engineering.infrastructure.task_models import Task, TaskEvent
from app.intake.domain.events import requirement_fingerprint


async def outcomes(session: AsyncSession, task_id: UUID) -> dict[str, Any]:
    task = await session.get(Task, task_id)
    if not task:
        raise LookupError("Comparison task not found")
    runs = list(
        await session.scalars(
            select(AIRun).where(AIRun.task_id == task_id).order_by(AIRun.started_at)
        )
    )
    developer = [run for run in runs if run.role_kind == "DEVELOPER"]
    validations = list(
        await session.scalars(
            select(ValidationRun)
            .where(ValidationRun.task_id == task_id)
            .order_by(ValidationRun.started_at)
        )
    )
    manual = await session.scalar(
        select(TaskEvent.id)
        .where(
            TaskEvent.task_id == task_id,
            TaskEvent.payload["action"].as_string() == "TAKEOVER",
        )
        .limit(1)
    )
    prices = [
        r.provider_cost_usd if r.provider_cost_usd is not None else r.calculated_cost_usd
        for r in runs
    ]
    cost = (
        sum((p for p in prices if p is not None), Decimal(0))
        if runs
        and all(p is not None and r.status != "RUNNING" for p, r in zip(prices, runs, strict=True))
        else None
    )
    current_validation = [
        v
        for v in validations
        if v.head_sha == task.current_revision and v.requirement_version == task.requirement_version
    ]
    batches = list(
        await session.scalars(
            select(TaskEvent)
            .where(
                TaskEvent.task_id == task_id,
                TaskEvent.source == "engineering",
                TaskEvent.event_type == "VALIDATION_BATCH_COMPLETED",
                TaskEvent.payload["requirement_version"].as_integer() == task.requirement_version,
            )
            .order_by(TaskEvent.id)
        )
    )
    model_ids = {
        request["provider"] + "/" + request["model"]
        for run in developer
        for request in (run.raw_usage or {}).get("priced_requests", [])
        if isinstance(request, dict)
        and isinstance(request.get("provider"), str)
        and isinstance(request.get("model"), str)
    }
    model_ids.update(
        run.provider + "/" + run.model
        for run in developer
        if not (run.raw_usage or {}).get("priced_requests")
    )
    return {
        "first_validation_passed": batches[0].payload["passed"] if batches else None,
        "validation_batches_observed": len(batches),
        "task_id": str(task_id),
        "requirement_fingerprint": requirement_fingerprint(
            task.title, await current_requirement(session, task)
        ),
        "models": sorted(model_ids),
        "status": task.status,
        "accepted_delivery": True
        if task.status == "MERGED"
        else False
        if task.status in {"FAILED", "CANCELLED"}
        else None,
        "human_takeover_observed": bool(manual or task.manual_takeover),
        "current_validation_passed": bool(current_validation)
        and all(v.status == "PASSED" for v in current_validation),
        "failed_validation_checks": sum(v.status == "FAILED" for v in validations),
        "developer_generations": len({r.session_id for r in developer if r.session_id}),
        "input_tokens": sum(r.input_tokens or 0 for r in runs)
        if runs and all(r.input_tokens is not None for r in runs)
        else None,
        "output_tokens": sum(r.output_tokens or 0 for r in runs)
        if runs and all(r.output_tokens is not None for r in runs)
        else None,
        "total_known_cost_usd": str(cost) if cost is not None else None,
        "time_to_merge_seconds": (task.completed_at - task.started_at).total_seconds()
        if task.completed_at and task.started_at
        else None,
    }


async def export(database_url: str, task_ids: list[UUID], output: Path) -> None:
    if not 1 <= len(task_ids) <= 100 or len(set(task_ids)) != len(task_ids):
        raise ValueError("Select between one and 100 distinct task UUIDs")
    if not database_url.startswith(("postgresql+asyncpg://", "postgresql+psycopg://")):
        raise ValueError("An explicit PostgreSQL URL is required")
    engine = create_async_engine(
        database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
    )
    try:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            rows = [await outcomes(session, task_id) for task_id in task_ids]
        with output.open("x") as stream:
            for row in rows:
                stream.write(json.dumps(row) + "\n")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--task-ids", type=UUID, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(export(os.environ[args.database_url_env], args.task_ids, args.output))
