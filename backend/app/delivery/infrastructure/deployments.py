"""Persist verified webhook facts and query bounded history without provider calls."""

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.delivery.domain.deployments import github_deployment
from app.delivery.infrastructure.deployment_models import DeploymentObservation
from app.repositories.infrastructure.models import Repository


async def record_deployment(
    session: AsyncSession, repository_id: UUID, kind: str, payload: dict[str, Any]
) -> None:
    fact = github_deployment(kind, payload)
    if fact is None:
        return
    await session.execute(
        insert(DeploymentObservation)
        .values(repository_id=repository_id, **asdict(fact))
        .on_conflict_do_nothing(constraint="uq_deployment_observation")
    )


def deployment_payload(row: DeploymentObservation) -> dict[str, Any]:
    return {
        "repository_id": str(row.repository_id),
        "deployment_id": row.deployment_id,
        "observation_id": row.observation_id,
        "head_sha": row.sha,
        "environment": row.environment,
        "production": row.production,
        "status": row.status,
        "started_at": row.started_at.isoformat(),
    }


class SqlDeploymentQueries:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def history(
        self, start: datetime, end: datetime, repository_id: UUID | None, limit: int
    ) -> dict[str, Any]:
        if (
            not start.tzinfo
            or not end.tzinfo
            or not start < end
            or end - start > timedelta(days=90)
        ):
            raise ValueError("Choose a timezone-aware range of at most 90 days")
        if not 1 <= limit <= 2000:
            raise ValueError("History limit must be between 1 and 2000")
        async with self.sessions.begin() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            await session.execute(text("SET LOCAL statement_timeout = '2s'"))
            if repository_id and await session.get(Repository, repository_id) is None:
                raise LookupError("Repository not found")
            query = (
                select(DeploymentObservation, Repository.owner, Repository.name)
                .join(Repository)
                .where(
                    DeploymentObservation.occurred_at >= start,
                    DeploymentObservation.occurred_at <= end,
                )
            )
            if repository_id:
                query = query.where(DeploymentObservation.repository_id == repository_id)
            rows = (
                await session.execute(
                    query.order_by(
                        DeploymentObservation.occurred_at, DeploymentObservation.id
                    ).limit(limit + 1)
                )
            ).all()
            return {
                "truncated": len(rows) > limit,
                "events": [
                    {
                        "id": str(row.id),
                        "repository": f"{owner}/{name}",
                        "occurred_at": row.occurred_at,
                        **deployment_payload(row),
                    }
                    for row, owner, name in rows[:limit]
                ],
            }
