"""Export recorded Coordinator situations for human labeling and offline/live replay.

No credentials or provider clients are read. The database transaction is read-only.
Recorded model decisions are observations, never automatically accepted as ground truth.
"""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.platform.persistence.registry  # noqa: F401 -- register persisted model relationships
from app.coordinator.infrastructure.models import CoordinatorRun


def history_case(run: CoordinatorRun) -> dict[str, Any]:
    situation = run.evidence["packet"]
    return {
        "id": "history:" + str(run.id),
        "source": "recorded_coordinator_situation",
        "task_id": str(run.task_id),
        "situation": situation,
        "situation_sha256": hashlib.sha256(
            json.dumps(situation, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "recorded_action": (run.decision or {}).get("action"),
        "expected_actions": [],
        "label_source": "UNLABELED",
    }


async def export(database_url: str, output: Path, limit: int) -> int:
    if not 1 <= limit <= 100:
        raise ValueError("Export limit must be between one and 100 situations")
    if not database_url.startswith(("postgresql+asyncpg://", "postgresql+psycopg://")):
        raise ValueError("An explicit PostgreSQL URL is required")
    engine = create_async_engine(
        database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
    )
    try:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            rows = list(
                await session.scalars(
                    select(CoordinatorRun)
                    .where(
                        CoordinatorRun.status.in_(["COMPLETED", "SHADOW"]),
                    )
                    .order_by(CoordinatorRun.created_at.desc())
                    .limit(limit)
                )
            )
            cases = [history_case(row) for row in rows if row.evidence.get("packet")]
        with output.open("x") as stream:
            for case in cases:
                stream.write(json.dumps(case, ensure_ascii=False) + "\n")
        return len(cases)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    count = asyncio.run(export(os.environ[args.database_url_env], args.output, args.limit))
    print(
        f"Exported {count} recorded situations. Label expected_actions and set label_source=HUMAN before live comparison."
    )
