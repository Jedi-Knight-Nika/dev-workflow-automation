from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
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
            if len(tasks) > 5000:
                raise ValueError("Analytics cohort exceeds 5000 tasks; select a smaller window")
            if not tasks:
                return []
            ids = [task.id for task in tasks]
            team_ids = {task.team_id for task in tasks if task.team_id}
            repository_ids = {task.repository_id for task in tasks if task.repository_id}
            teams = {
                task.id: task
                for task in await session.scalars(select(Team).where(Team.id.in_(team_ids)))
            }
            repositories = {
                repository.id: repository
                for repository in await session.scalars(
                    select(Repository).where(Repository.id.in_(repository_ids))
                )
            }
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
            for run, profile_id, profile_name in rows:
                raw = run.raw_usage or {}
                if (
                    raw.get("run_kind") == "DEVELOPER_COMPACTION"
                    or "compact" in run.prompt_version.lower()
                    or raw.get("compaction")
                ):
                    kind = "DEVELOPER_COMPACTION"
                elif run.role_kind == "DEVELOPER":
                    kind = "DEVELOPER_TURN"
                elif run.role_kind == "INTERPRETER":
                    kind = "INTERPRETER_CLOUD"
                else:
                    kind = run.role_kind
                runs.setdefault(run.task_id, []).append(
                    RunFact(
                        id=str(run.id),
                        task_id=str(run.task_id),
                        profile_id=str(profile_id) if profile_id else None,
                        provider=run.provider,
                        model=run.model,
                        harness=run.harness,
                        role=run.role_kind,
                        run_kind=kind,
                        status=run.status,
                        started_at=run.started_at,
                        finished_at=run.finished_at,
                        cost=run.provider_cost_usd
                        if run.provider_cost_usd is not None
                        else run.calculated_cost_usd,
                        reserved=run.reserved_cost_usd,
                        input_tokens=run.input_tokens,
                        output_tokens=run.output_tokens,
                        cache_read_tokens=run.cache_read_tokens,
                        cache_write_tokens=run.cache_write_tokens,
                        reasoning_tokens=run.reasoning_tokens,
                        usage_complete=run.usage_complete,
                        provider_duration_ms=run.provider_duration_ms,
                        profile_name=profile_name,
                        context_tokens=raw.get("context_tokens")
                        if isinstance(raw.get("context_tokens"), int)
                        else None,
                        first_edit_at=None,
                        failure_code=run.failure_code,
                        long_context_tier=str(raw.get("context_tier", "")).lower()
                        in {"long", "long_context", "above_272k"},
                    )
                )
            phases: dict[UUID, list[dict[str, Any]]] = {}
            for phase in await session.scalars(
                select(TaskPhaseRun).where(TaskPhaseRun.task_id.in_(ids))
            ):
                phases.setdefault(phase.task_id, []).append(
                    {
                        "stage": phase.stage,
                        "status": phase.status,
                        "wait_reason": phase.wait_reason,
                        "started_at": phase.started_at.isoformat(),
                        "finished_at": phase.finished_at.isoformat() if phase.finished_at else None,
                        "seconds": (phase.finished_at - phase.started_at).total_seconds()
                        if phase.finished_at
                        else None,
                    }
                )
            reviews = {
                task_id: count
                for task_id, count in (
                    await session.execute(
                        select(ReviewCycle.task_id, func.count())
                        .where(
                            ReviewCycle.task_id.in_(ids),
                            ReviewCycle.decision.in_(["CODE_CHANGE", "ARCHITECTURE_CHANGE"]),
                        )
                        .group_by(ReviewCycle.task_id)
                    )
                ).all()
            }
            failures = {
                task_id: count
                for task_id, count in (
                    await session.execute(
                        select(ValidationRun.task_id, func.count())
                        .where(ValidationRun.task_id.in_(ids), ValidationRun.status != "PASSED")
                        .group_by(ValidationRun.task_id)
                    )
                ).all()
            }
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
                profile.team_id: profile
                for profile in await session.scalars(
                    select(TeamAgentProfile).where(
                        TeamAgentProfile.team_id.in_(team_ids),
                        TeamAgentProfile.role_kind == "DEVELOPER",
                    )
                )
            }
            local: dict[UUID, list[dict[str, Any]]] = {}
            for run in await session.scalars(
                select(LocalModelRun).where(LocalModelRun.task_id.in_(ids))
            ):
                local.setdefault(run.task_id, []).append(
                    {
                        "model": run.model,
                        "status": run.status,
                        "duration_ms": run.duration_ms,
                        "input_tokens": run.input_tokens,
                        "output_tokens": run.output_tokens,
                        "started_at": run.started_at.isoformat(),
                        "run_kind": "INTERPRETER_LOCAL",
                    }
                )
            return [
                TaskFact(
                    id=str(task.id),
                    title=task.title,
                    team_id=str(task.team_id) if task.team_id else None,
                    repository_id=str(task.repository_id) if task.repository_id else None,
                    source=(task.external_key or "manual").split("-")[0].lower(),
                    description_length=len(task.description or ""),
                    status=task.status,
                    created_at=task.created_at,
                    completed_at=task.completed_at,
                    runs=runs.get(task.id, []),
                    phases=phases.get(task.id, []),
                    review_cycles=reviews.get(task.id, 0),
                    validation_failures=failures.get(task.id, 0),
                    peak_memory=peaks.get(task.id),
                    planned_harness=planned[task.team_id].harness
                    if task.team_id in planned
                    else None,
                    planned_model=planned[task.team_id].model if task.team_id in planned else None,
                    local_runs=local.get(task.id, []),
                    estimate=float(task.estimate) if task.estimate is not None else None,
                    labels=task.labels,
                    repository_name=f"{repositories[task.repository_id].owner}/{repositories[task.repository_id].name}"
                    if task.repository_id in repositories
                    else None,
                    team_name=teams[task.team_id].name if task.team_id in teams else None,
                    concurrency=teams[task.team_id].max_concurrent_tasks
                    if task.team_id in teams
                    else 1,
                )
                for task in tasks
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
