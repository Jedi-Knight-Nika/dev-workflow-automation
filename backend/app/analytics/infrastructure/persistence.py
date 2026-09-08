from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.analytics.domain.efficiency import RunFact, TaskFact
from app.analytics.infrastructure.models import TaskForecast
from app.engineering.infrastructure.models import ReviewCycle, TaskPhaseRun, ValidationRun
from app.engineering.infrastructure.task_models import Task
from app.intake.infrastructure.models import LocalModelRun
from app.observability.infrastructure.models import RunnerResourceBinding, RunnerResourceSummary
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team


class SqlAnalyticsFacts:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def tasks(
        self, since: datetime, team_id: UUID | None = None, task_id: UUID | None = None
    ) -> list[TaskFact]:
        async with self.sessions() as session:
            query = select(Task)
            if task_id:
                query = query.where(Task.id == task_id)
            else:
                query = query.where(
                    or_(
                        Task.created_at >= since,
                        Task.completed_at >= since,
                        Task.id.in_(select(AIRun.task_id).where(AIRun.started_at >= since)),
                    )
                )
            if team_id:
                query = query.where(Task.team_id == team_id)
            tasks = list(await session.scalars(query.order_by(Task.created_at.desc()).limit(5001)))
            teams = {
                t.id: t
                for t in await session.scalars(
                    select(Team).where(Team.id.in_([t.team_id for t in tasks if t.team_id]))
                )
            }
            repos = {
                r.id: r
                for r in await session.scalars(
                    select(Repository).where(
                        Repository.id.in_([t.repository_id for t in tasks if t.repository_id])
                    )
                )
            }
            if len(tasks) > 5000:
                raise ValueError("Analytics cohort exceeds 5000 tasks; select a smaller window")
            ids = [t.id for t in tasks]
            if not ids:
                return []
            rows = (
                await session.execute(
                    select(AIRun, DeveloperSession.profile_id, TeamAgentProfile.display_name)
                    .outerjoin(DeveloperSession, DeveloperSession.id == AIRun.session_id)
                    .outerjoin(TeamAgentProfile, TeamAgentProfile.id == DeveloperSession.profile_id)
                    .where(AIRun.task_id.in_(ids))
                    .limit(50001)
                )
            ).all()
            if len(rows) > 50000:
                raise ValueError("Analytics run cohort exceeds bound")
            runs: dict[UUID, list[RunFact]] = {}
            for r, profile, profile_name in rows:
                raw = r.raw_usage or {}
                kind = (
                    "DEVELOPER_COMPACTION"
                    if raw.get("run_kind") == "DEVELOPER_COMPACTION"
                    or "compact" in r.prompt_version.lower()
                    or raw.get("compaction")
                    else "DEVELOPER_TURN"
                    if r.role_kind == "DEVELOPER"
                    else "INTERPRETER_CLOUD"
                    if r.role_kind == "INTERPRETER"
                    else r.role_kind
                )
                runs.setdefault(r.task_id, []).append(
                    RunFact(
                        str(r.id),
                        str(r.task_id),
                        str(profile) if profile else None,
                        r.provider,
                        r.model,
                        r.harness,
                        r.role_kind,
                        kind,
                        r.status,
                        r.started_at,
                        r.finished_at,
                        r.provider_cost_usd
                        if r.provider_cost_usd is not None
                        else r.calculated_cost_usd,
                        r.reserved_cost_usd,
                        r.input_tokens,
                        r.output_tokens,
                        r.cache_read_tokens,
                        r.cache_write_tokens,
                        r.reasoning_tokens,
                        r.usage_complete,
                        r.provider_duration_ms,
                        profile_name,
                        raw.get("context_tokens")
                        if isinstance(raw.get("context_tokens"), int)
                        else None,
                        None,
                        r.failure_code,
                        str(raw.get("context_tier", "")).lower()
                        in {"long", "long_context", "above_272k"},
                    )
                )
            phases: dict[UUID, list[dict[str, Any]]] = {}
            for p in await session.scalars(
                select(TaskPhaseRun).where(TaskPhaseRun.task_id.in_(ids))
            ):
                phases.setdefault(p.task_id, []).append(
                    {
                        "stage": p.stage,
                        "status": p.status,
                        "wait_reason": p.wait_reason,
                        "started_at": p.started_at.isoformat(),
                        "finished_at": p.finished_at.isoformat() if p.finished_at else None,
                        "seconds": (p.finished_at - p.started_at).total_seconds()
                        if p.finished_at
                        else None,
                    }
                )
            reviews: dict[UUID, int] = {}
            for review in await session.scalars(
                select(ReviewCycle).where(ReviewCycle.task_id.in_(ids))
            ):
                if review.decision in {"CODE_CHANGE", "ARCHITECTURE_CHANGE"}:
                    reviews[review.task_id] = reviews.get(review.task_id, 0) + 1
            failures: dict[UUID, int] = {}
            for validation in await session.scalars(
                select(ValidationRun).where(
                    ValidationRun.task_id.in_(ids), ValidationRun.status != "PASSED"
                )
            ):
                failures[validation.task_id] = failures.get(validation.task_id, 0) + 1
            peaks: dict[UUID, float] = {}
            for binding, summary in (
                await session.execute(
                    select(RunnerResourceBinding, RunnerResourceSummary)
                    .join(
                        RunnerResourceSummary,
                        RunnerResourceSummary.runner_run_id == RunnerResourceBinding.runner_run_id,
                    )
                    .where(
                        RunnerResourceBinding.task_id.in_(ids),
                        RunnerResourceSummary.metrics_complete.is_(True),
                    )
                )
            ).all():
                value = summary.values.get("max_memory_bytes")
                if value is not None:
                    peaks[binding.task_id] = max(peaks.get(binding.task_id, 0), value)
            planned = {
                p.team_id: p
                for p in await session.scalars(
                    select(TeamAgentProfile).where(
                        TeamAgentProfile.team_id.in_([t.team_id for t in tasks if t.team_id]),
                        TeamAgentProfile.role_kind == "DEVELOPER",
                    )
                )
            }
            local: dict[UUID, list[dict[str, Any]]] = {}
            for r in await session.scalars(
                select(LocalModelRun).where(LocalModelRun.task_id.in_(ids))
            ):
                local.setdefault(r.task_id, []).append(
                    {
                        "model": r.model,
                        "status": r.status,
                        "duration_ms": r.duration_ms,
                        "input_tokens": r.input_tokens,
                        "output_tokens": r.output_tokens,
                        "started_at": r.started_at.isoformat(),
                        "run_kind": "INTERPRETER_LOCAL",
                    }
                )
            return [
                TaskFact(
                    str(t.id),
                    t.title,
                    str(t.team_id) if t.team_id else None,
                    str(t.repository_id) if t.repository_id else None,
                    (t.external_key or "manual").split("-")[0].lower(),
                    len(t.description or ""),
                    t.status,
                    t.created_at,
                    t.completed_at,
                    runs.get(t.id, []),
                    phases.get(t.id, []),
                    reviews.get(t.id, 0),
                    failures.get(t.id, 0),
                    peaks.get(t.id),
                    planned[t.team_id].harness if t.team_id in planned else None,
                    planned[t.team_id].model if t.team_id in planned else None,
                    local.get(t.id, []),
                    float(t.estimate) if t.estimate is not None else None,
                    t.labels,
                    f"{repos[t.repository_id].owner}/{repos[t.repository_id].name}"
                    if t.repository_id in repos
                    else None,
                    teams[t.team_id].name if t.team_id in teams else None,
                    teams[t.team_id].max_concurrent_tasks if t.team_id in teams else 1,
                )
                for t in tasks
            ]

    async def forecast_snapshots(self, task_id: UUID | None = None) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            query = select(TaskForecast)
            if task_id:
                query = query.where(TaskForecast.task_id == task_id)
            return [
                {
                    "id": str(f.id),
                    "task_id": str(f.task_id),
                    "created_at": f.created_at.isoformat(),
                    "forecast_version": f.forecast_version,
                    "confidence": f.confidence,
                    "sample_count": f.sample_count,
                    "estimate": f.estimates,
                    "range": {key: value.get("range") for key, value in f.estimates.items()},
                    "actuals": f.actuals,
                    "finalized_at": f.finalized_at.isoformat() if f.finalized_at else None,
                }
                for f in await session.scalars(
                    query.order_by(TaskForecast.created_at.desc()).limit(1000)
                )
            ]
