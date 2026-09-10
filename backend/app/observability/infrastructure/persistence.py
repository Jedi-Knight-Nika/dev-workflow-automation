from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only

from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.infrastructure.task_models import Task
from app.observability.infrastructure.models import (
    ContainerObservation,
    InfrastructureEvent,
    RunnerResourceBinding,
    RunnerResourceSummary,
    ServiceIncident,
)
from app.teams.infrastructure.models import TeamAgentProfile


def columns(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def receipt_totals(receipts: list[AIRun], now: datetime) -> dict[str, Any]:
    """Task-wide display totals; missing measurements retain their existing semantics."""
    costs = [
        r.provider_cost_usd if r.provider_cost_usd is not None else r.calculated_cost_usd
        for r in receipts
    ]
    return {
        "known_cost_usd": str(sum(c for c in costs if c is not None)),
        "unknown_cost_runs": sum(c is None for c in costs),
        "input_tokens": sum(r.input_tokens for r in receipts if r.input_tokens is not None)
        if all(r.input_tokens is not None for r in receipts)
        else None,
        "output_tokens": sum(r.output_tokens for r in receipts if r.output_tokens is not None)
        if all(r.output_tokens is not None for r in receipts)
        else None,
        "developer_active_seconds": sum(
            ((r.finished_at or now) - r.started_at).total_seconds()
            for r in receipts
            if r.role_kind == "DEVELOPER"
        ),
        "ai_active_seconds": sum(
            r.provider_duration_ms for r in receipts if r.provider_duration_ms is not None
        )
        / 1000
        if receipts and all(r.provider_duration_ms is not None for r in receipts)
        else None,
        "usage_basis": "Task receipts to date; resource values belong to this container",
    }


class SqlObservabilityStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def containers(self) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            return [
                {"container_id": r.container_id, **r.values, "observed_at": r.sampled_at}
                for r in await session.scalars(
                    select(ContainerObservation)
                    .where(
                        ContainerObservation.sampled_at >= datetime.now(UTC) - timedelta(seconds=45)
                    )
                    .limit(200)
                )
            ]

    async def runners(
        self, task_id: UUID | None = None, active: bool = False
    ) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            query = select(RunnerResourceBinding, RunnerResourceSummary).outerjoin(
                RunnerResourceSummary,
                RunnerResourceSummary.runner_run_id == RunnerResourceBinding.runner_run_id,
            )
            if task_id:
                query = query.where(RunnerResourceBinding.task_id == task_id)
            if active:
                query = query.where(RunnerResourceBinding.stopped_at.is_(None))
            result = [
                {**columns(binding), "summary": columns(summary) if summary else None}
                for binding, summary in (
                    await session.execute(
                        query.order_by(RunnerResourceBinding.started_at.desc()).limit(200)
                    )
                ).all()
            ]
            if not result:
                return []
            task_ids = {r["task_id"] for r in result if r["task_id"]}
            tasks = {
                t.id: t
                for t in await session.scalars(
                    select(Task)
                    .options(load_only(Task.title, Task.external_key, raiseload=True))
                    .where(Task.id.in_(task_ids))
                )
            }
            profiles = {
                p.id: p
                for p in await session.scalars(
                    select(TeamAgentProfile)
                    .options(
                        load_only(
                            TeamAgentProfile.display_name,
                            TeamAgentProfile.harness,
                            TeamAgentProfile.model,
                            raiseload=True,
                        )
                    )
                    .where(
                        TeamAgentProfile.id.in_(
                            [r["agent_profile_id"] for r in result if r["agent_profile_id"]]
                        )
                    )
                )
            }
            runs: dict[UUID, list[AIRun]] = {}
            for run in await session.scalars(
                select(AIRun)
                .options(
                    load_only(
                        AIRun.task_id,
                        AIRun.provider_cost_usd,
                        AIRun.calculated_cost_usd,
                        AIRun.input_tokens,
                        AIRun.output_tokens,
                        AIRun.started_at,
                        AIRun.finished_at,
                        AIRun.role_kind,
                        AIRun.provider_duration_ms,
                        raiseload=True,
                    )
                )
                .where(AIRun.task_id.in_(task_ids))
            ):
                runs.setdefault(run.task_id, []).append(run)
            now = datetime.now(UTC)
            usage = {task_id: receipt_totals(receipts, now) for task_id, receipts in runs.items()}
            empty_usage = receipt_totals([], now)
            for row in result:
                task = tasks.get(row["task_id"])
                profile = profiles.get(row["agent_profile_id"])
                row.update(
                    task_title=task.title if task else None,
                    task_key=task.external_key if task else None,
                    profile_name=profile.display_name if profile else None,
                    harness=profile.harness if profile else None,
                    model=profile.model if profile else None,
                    **usage.get(row["task_id"], empty_usage),
                )
            return result

    async def runner(self, runner_id: UUID) -> dict[str, Any] | None:
        async with self.sessions() as session:
            binding = await session.scalar(
                select(RunnerResourceBinding).where(
                    RunnerResourceBinding.runner_run_id == runner_id
                )
            )
            if binding is None:
                return None
            summary = await session.get(RunnerResourceSummary, runner_id)
            return {**columns(binding), "summary": columns(summary) if summary else None}

    async def incidents(self, days: int, incident_id: UUID | None = None) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            query = select(ServiceIncident)
            if incident_id:
                query = query.where(ServiceIncident.id == incident_id)
            else:
                query = query.where(
                    or_(
                        ServiceIncident.closed_at.is_(None),
                        ServiceIncident.closed_at >= datetime.now(UTC) - timedelta(days=days),
                    )
                )
            return [
                columns(i)
                for i in await session.scalars(
                    query.order_by(ServiceIncident.opened_at.desc()).limit(200)
                )
            ]

    async def events(self, days: int) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            return [
                columns(e)
                for e in await session.scalars(
                    select(InfrastructureEvent)
                    .where(
                        InfrastructureEvent.occurred_at >= datetime.now(UTC) - timedelta(days=days)
                    )
                    .order_by(InfrastructureEvent.occurred_at.desc())
                    .limit(200)
                )
            ]

    async def task_events(self, task_id: UUID) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            return [
                columns(event)
                for event in await session.scalars(
                    select(InfrastructureEvent)
                    .join(
                        RunnerResourceBinding,
                        RunnerResourceBinding.runner_run_id == InfrastructureEvent.runner_run_id,
                    )
                    .where(RunnerResourceBinding.task_id == task_id)
                    .order_by(InfrastructureEvent.occurred_at.desc())
                    .limit(200)
                )
            ]

    async def alert(
        self,
        key: str,
        service: str,
        kind: str,
        severity: str,
        opened: datetime,
        closed: datetime | None,
    ) -> None:
        async with self.sessions.begin() as session:
            statement = insert(ServiceIncident).values(
                dedup_key=key,
                service_key=service,
                kind=kind,
                severity=severity,
                opened_at=opened,
                closed_at=closed,
                source="alertmanager",
                summary=f"{service}: {kind}",
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[ServiceIncident.dedup_key], set_={"closed_at": closed}
                )
                if closed
                else statement.on_conflict_do_nothing(index_elements=[ServiceIncident.dedup_key])
            )
