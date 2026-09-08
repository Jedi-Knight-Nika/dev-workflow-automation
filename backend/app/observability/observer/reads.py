"""Anti-corruption adapter: bounded, read-only projections, never raw logs/prompts."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import UUID

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only
from sqlalchemy.sql.elements import ColumnElement

from app.agent_runtime.infrastructure.models import AIRun
from app.analytics.application.ports import AnalyticsQueries
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.observability.application.ports import ObservabilityQueries, ObservabilityStore
from app.observability.observer.domain import Evidence, Scope, Snapshot, number
from app.teams.infrastructure.automation import TeamAutomationPolicy
from app.teams.infrastructure.team_models import Team

PRODUCT_FACTS = (
    "I am a read-only operations companion. I can explain tasks, AI receipts, resources, incidents and forecasts; I cannot change tasks, budgets, repositories or containers.",
    "The fixed delivery flow is intake → one native Developer → offline validation → publication → review wait → conditional merge. Waiting does not purchase Developer model calls.",
    "PostgreSQL AI receipts are billing truth. Prometheus measures infrastructure. Missing readings are unknown, not zero or confirmed downtime.",
    "Optional local Ollama inference has separate accounting, no paid cloud fallback and no access to source, shell, secrets or Developer transcripts. When capacity is unavailable I answer deterministically.",
    "I use current read-only product facts, not training on your repository. New capabilities can be added behind my typed query boundary without changing engineering execution.",
)


class ProductObserverReads:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        metrics: Callable[[], Awaitable[ObservabilityQueries]],
        analytics: Callable[[], Awaitable[AnalyticsQueries]],
        incidents: ObservabilityStore,
    ) -> None:
        self.sessions, self.metrics, self.analytics, self.incidents = (
            sessions,
            metrics,
            analytics,
            incidents,
        )
        self.cache: dict[Scope, tuple[float, Snapshot]] = {}
        self.lock = asyncio.Lock()

    async def execution_busy(self) -> bool:
        async with self.sessions() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            return bool(
                await session.scalar(
                    select(Job.id).where(Job.state.in_(["QUEUED", "CLAIMED", "RUNNING"])).limit(1)
                )
            )

    async def snapshot(self, scope: Scope, *, fresh: bool = False) -> Snapshot:
        async with asyncio.timeout(12), self.lock:
            old = self.cache.get(scope)
            if not fresh and old and monotonic() - old[0] < 20:
                return old[1]
            snap = Snapshot(datetime.now(UTC).isoformat())
            try:
                await self._tasks(scope, snap)
            except LookupError:
                raise
            except Exception:  # noqa: BLE001 -- read-model boundary, never infer missing facts
                snap.partial_sources.extend(["TASKS", "AI_RUNS"])
            try:
                async with asyncio.timeout(6):
                    live = await (await self.metrics()).live()
                snap.host, snap.metrics_at = live.get("host", {}), live.get("sampled_at")
                last_seen = number(snap.host.get("host_last_seen"))
                if last_seen is None or datetime.now(UTC).timestamp() - last_seen > 60:
                    snap.host = {}
                    snap.metrics_at = None
                snap.services = live.get("services", [])[:50]
                if live.get("status") != "available" or not snap.metrics_at:
                    snap.partial_sources.append("PROMETHEUS")
            except Exception:  # noqa: BLE001 -- optional metrics boundary
                snap.partial_sources.append("PROMETHEUS")
            try:
                async with asyncio.timeout(3):
                    snap.incidents = [
                        {
                            key: value.isoformat()
                            if isinstance(value, datetime)
                            else str(value)
                            if isinstance(value, UUID)
                            else value
                            for key, value in row.items()
                        }
                        for row in (await self.incidents.incidents(30))[:100]
                    ]
            except Exception:  # noqa: BLE001 -- independent incident source
                snap.partial_sources.append("INCIDENTS")
            if len(self.cache) >= 32:
                self.cache.pop(next(iter(self.cache)))
            self.cache[scope] = monotonic(), snap
            return snap

    async def _tasks(self, scope: Scope, snap: Snapshot) -> None:
        async with self.sessions() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            if scope.team_id and not await session.scalar(
                select(Team.id).where(Team.id == UUID(scope.team_id))
            ):
                raise LookupError("Team not found in this scope.")
            filters: list[ColumnElement[bool]] = [Task.archived_at.is_(None)]
            if scope.task_id:
                filters.append(Task.id == UUID(scope.task_id))
            if scope.team_id:
                filters.append(Task.team_id == UUID(scope.team_id))
            snap.counts = {
                status: count
                for status, count in (
                    await session.execute(
                        select(Task.status, func.count()).where(*filters).group_by(Task.status)
                    )
                ).all()
            }
            if scope.task_id and not snap.counts:
                raise LookupError("Task not found in this scope.")
            task_rows = list(
                await session.scalars(
                    select(Task)
                    .options(
                        load_only(
                            Task.id,
                            Task.external_key,
                            Task.title,
                            Task.team_id,
                            Task.status,
                            Task.stage,
                            Task.wait_reason,
                            Task.requirement_version,
                            Task.updated_at,
                            Task.no_progress_count,
                        )
                    )
                    .where(*filters)
                    .order_by(
                        case((Task.status.in_(["ACTIVE", "WAITING_HUMAN", "FAILED"]), 0), else_=1),
                        Task.updated_at.desc(),
                    )
                    .limit(101)
                )
            )
            snap.tasks_truncated = len(task_rows) > 100
            task_rows = task_rows[:100]
            ids = [t.id for t in task_rows]
            cost = func.coalesce(AIRun.provider_cost_usd, AIRun.calculated_cost_usd)
            usage = {
                r.task_id: r
                for r in (
                    await session.execute(
                        select(
                            AIRun.task_id,
                            func.sum(cost).label("known"),
                            func.count().label("runs"),
                            func.count().filter(cost.is_(None)).label("unknown"),
                            func.count()
                            .filter(cost.is_(None), AIRun.status != "RUNNING")
                            .label("unknown_stopped"),
                            func.sum(AIRun.input_tokens).label("input"),
                            func.count(AIRun.input_tokens).label("input_count"),
                            func.sum(AIRun.output_tokens).label("output"),
                            func.count(AIRun.output_tokens).label("output_count"),
                            func.sum(AIRun.cache_read_tokens).label("cached"),
                            func.count(AIRun.cache_read_tokens).label("cached_count"),
                            func.max(AIRun.active_context_estimate).label("context"),
                        )
                        .where(AIRun.task_id.in_(ids))
                        .group_by(AIRun.task_id)
                    )
                ).all()
            }
            policies = {
                p.team_id: p.configuration
                for p in await session.scalars(
                    select(TeamAutomationPolicy).where(
                        TeamAutomationPolicy.team_id.in_(
                            [t.team_id for t in task_rows if t.team_id]
                        )
                    )
                )
            }
            validations: dict[UUID, list[str]] = {}
            for validation in await session.scalars(
                select(ValidationRun)
                .where(ValidationRun.task_id.in_(ids))
                .order_by(ValidationRun.started_at.desc())
                .limit(2000)
            ):
                validations.setdefault(validation.task_id, []).append(validation.status)
            for task in task_rows:
                run = usage.get(task.id)
                failures = 0
                for status in validations.get(task.id, []):
                    if status not in {"FAILED", "TIMED_OUT"}:
                        break
                    failures += 1
                snap.tasks.append(
                    {
                        "id": str(task.id),
                        "label": task.external_key or str(task.id)[:8],
                        "title": task.title[:120],
                        "team_id": str(task.team_id) if task.team_id else None,
                        "status": task.status,
                        "stage": task.stage,
                        "wait_reason": task.wait_reason,
                        "requirement_version": task.requirement_version,
                        "updated_at": task.updated_at.isoformat(),
                        "known_cost_usd": str(run.known or 0) if run else "0",
                        "unknown_cost_runs": run.unknown if run else 0,
                        "unknown_stopped_runs": run.unknown_stopped if run else 0,
                        "input_tokens": run.input if run and run.input_count == run.runs else None,
                        "output_tokens": run.output
                        if run and run.output_count == run.runs
                        else None,
                        "cached_tokens": run.cached
                        if run and run.cached_count == run.runs
                        else None,
                        "context_peak_tokens": run.context if run else None,
                        "runs": run.runs if run else 0,
                        "budget_usd": policies.get(task.team_id, {}).get("task_budget_usd")
                        if task.team_id
                        else None,
                        "no_progress_count": task.no_progress_count,
                        "consecutive_validation_failures": failures,
                    }
                )
            # Global capacity, even on a scoped page. Conservatively yield to all
            # actionable jobs, including intake/Interpreter work.
            snap.busy = bool(
                await session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.state.in_(["QUEUED", "CLAIMED", "RUNNING"]))
                )
            )

    async def evidence(
        self, tool: str, scope: Scope, days: int, since: str | None
    ) -> list[Evidence]:
        snap = await self.snapshot(scope)
        result: list[Evidence] = []

        def add(key: str, sentence: str, source: str = "TASKS", complete: bool = True) -> None:
            result.append(
                Evidence(
                    f"{tool}:{key}",
                    sentence,
                    source,
                    snap.metrics_at if source == "PROMETHEUS" else snap.measured_at,
                    complete and source not in snap.partial_sources,
                )
            )

        if tool == "product":
            return [
                Evidence(f"product:{i}", fact, "PRODUCT_CONTRACT", None)
                for i, fact in enumerate(PRODUCT_FACTS)
            ]
        if tool == "tasks":
            add(
                "counts",
                "Tasks in this scope: "
                + (
                    ", ".join(
                        f"{count} {status.lower().replace('_', ' ')}"
                        for status, count in snap.counts.items()
                    )
                    or "none"
                )
                + ".",
            )
            for task in snap.tasks[:6]:
                add(
                    task["id"],
                    f"{task['label']}: {task['stage'].lower()}, {task['status'].lower().replace('_', ' ')}; wait reason {task['wait_reason'].lower().replace('_', ' ')}. "
                    f"{task['consecutive_validation_failures']} consecutive recent validation failures; {task['no_progress_count']} no-progress reports.",
                )
            if scope.task_id:
                value = await (await self.analytics()).task(UUID(scope.task_id))
                if value:
                    for key in (
                        "developer_active_seconds",
                        "human_or_external_wait_seconds",
                        "provider_active_seconds",
                        "review_cycles",
                    ):
                        add(
                            key,
                            f"{key.replace('_', ' ').capitalize()}: {value.get(key) if value.get(key) is not None else 'unavailable'}.",
                        )
        elif tool == "ai_usage":
            if scope.task_id:
                task = snap.tasks[0]
                add(
                    "receipt",
                    f"{task['label']}: ${task['known_cost_usd']} known AI cost across {task['runs']} runs; {task['unknown_cost_runs']} runs have unknown cost.",
                    "AI_RUNS",
                    not task["unknown_cost_runs"],
                )
                add(
                    "tokens",
                    f"Input {task['input_tokens'] if task['input_tokens'] is not None else 'unknown'}; cached input {task['cached_tokens'] if task['cached_tokens'] is not None else 'unknown'}; output {task['output_tokens'] if task['output_tokens'] is not None else 'unknown'}. Cached tokens are a subset of input, not an extra charge category to sum again.",
                    "AI_RUNS",
                )
                value = await (await self.analytics()).task(UUID(scope.task_id))
                if value:
                    runs = sorted(
                        value.get("runs", []),
                        key=lambda r: number(r.get("cost")) or -1,
                        reverse=True,
                    )
                    for run in runs[:3]:
                        add(
                            str(run["id"]),
                            f"{run['run_kind']} on {run['model']}: cost {run['cost'] if run['cost'] is not None else 'unknown'} USD, input {run['input_tokens']}, output {run['output_tokens']}; {run['status'].lower()}.",
                            "AI_RUNS",
                            run["cost"] is not None,
                        )
            else:
                dashboard = await (await self.analytics()).dashboard(
                    days, UUID(scope.team_id) if scope.team_id else None
                )
                totals = dashboard["totals"]
                add(
                    "total",
                    f"Last {days} days: ${totals['known_cost_usd']} known AI cost, {totals['unknown_cost_runs']} unknown-cost runs. Cost per complete merged task: {dashboard.get('cost_per_merged_task_usd') or 'unavailable'} USD.",
                    "AI_RUNS",
                    totals["cost_complete"],
                )
                for agent in sorted(
                    dashboard.get("agents", []),
                    key=lambda a: number(a.get("known_cost_usd")) or 0,
                    reverse=True,
                )[:4]:
                    add(
                        str(agent["key"]),
                        f"{agent['display_name']}: ${agent['known_cost_usd']} known cost, {agent['tasks_merged']} merged / {agent['terminal_tasks']} terminal tasks; median cost {agent['median_cost_usd']} USD. Compare cohort size before judging performance.",
                        "AI_RUNS",
                        agent["cost_complete"],
                    )
                for model in sorted(
                    dashboard.get("models", []),
                    key=lambda a: number(a.get("known_cost_usd")) or 0,
                    reverse=True,
                )[:3]:
                    add(
                        str(model["key"]),
                        f"{model['key']}: ${model['known_cost_usd']} known cost across {model['runs']} runs, input {model['input_tokens']}, output {model['output_tokens']}.",
                        "AI_RUNS",
                        model["cost_complete"],
                    )
        elif tool == "resources":
            for key, label in (("host_cpu", "CPU"), ("host_memory", "RAM"), ("host_disk", "Disk")):
                measurement = number(snap.host.get(key))
                add(
                    key,
                    f"Host {label}: {measurement:.1f}%."
                    if measurement is not None
                    else f"Host {label} is unavailable.",
                    "PROMETHEUS",
                    measurement is not None,
                )
            for service in sorted(
                snap.services, key=lambda s: number(s.get("memory")) or -1, reverse=True
            )[:4]:
                memory = number(service.get("memory"))
                name = service.get("service") or service.get("name") or "Container"
                add(
                    str(service["id"]),
                    f"{str(name)[:80]}: {memory / 1024**3:.2f} GiB working memory."
                    if memory is not None
                    else f"{str(name)[:80]}: memory unavailable.",
                    "PROMETHEUS",
                    memory is not None,
                )
            add(
                "capacity",
                "Capacity advice is advisory only. Current engineering work takes priority; free RAM alone does not prove another runner is safe to admit.",
                "PRODUCT_CONTRACT",
            )
        elif tool == "incidents":
            for incident in snap.incidents[:8]:
                add(
                    str(incident["id"]),
                    f"{incident.get('service_key')}: {incident.get('kind')} opened {incident.get('opened_at')}; "
                    + (
                        f"resolved {incident['closed_at']}."
                        if incident.get("closed_at")
                        else "still open."
                    ),
                    "INCIDENTS",
                )
            if not result:
                add(
                    "none",
                    "No incidents are recorded in the retained 30-day view. This does not prove uninterrupted availability.",
                    "INCIDENTS",
                )
        elif tool == "changes":
            start = (
                datetime.fromisoformat(since) if since else datetime.now(UTC) - timedelta(days=1)
            )
            async with self.sessions() as session:
                await session.execute(text("SET TRANSACTION READ ONLY"))
                query = (
                    select(TaskEvent.event_type, TaskEvent.created_at, TaskEvent.task_id)
                    .join(Task, Task.id == TaskEvent.task_id)
                    .where(TaskEvent.created_at >= start)
                )
                if scope.task_id:
                    query = query.where(Task.id == UUID(scope.task_id))
                if scope.team_id:
                    query = query.where(Task.team_id == UUID(scope.team_id))
                for i, row in enumerate(
                    (
                        await session.execute(query.order_by(TaskEvent.created_at.desc()).limit(8))
                    ).all()
                ):
                    add(
                        str(i),
                        f"{row.created_at.isoformat()}: task {str(row.task_id)[:8]} · {row.event_type.replace('_', ' ').lower()}.",
                    )
            if not result:
                add("none", "No recorded task events since " + start.isoformat() + ".")
        elif tool == "forecasts":
            queries = await self.analytics()
            forecast_value = (
                await queries.forecast_task(UUID(scope.task_id))
                if scope.task_id
                else await queries.forecast_queue(UUID(scope.team_id) if scope.team_id else None)
            )
            forecast_value = forecast_value or {}
            add(
                "forecast",
                f"Forecast confidence: {forecast_value.get('confidence', 'UNAVAILABLE')}; sample count {forecast_value.get('sample_count', 0)}. Forecasts are statistical advice, never spending authority.",
                "FORECASTS",
            )
            if scope.task_id:
                estimate = (forecast_value.get("estimate") or {}).get("cost_usd", {})
                add(
                    "cost",
                    f"Estimated task cost: {estimate.get('estimate', 'unavailable')} USD; P90 {estimate.get('range', {}).get('p90', 'unavailable')} USD.",
                    "FORECASTS",
                )
            else:
                add(
                    "cost",
                    f"Queued work: {forecast_value.get('queued_tasks', 'unknown')} tasks; estimated cost {forecast_value.get('estimate', 'unavailable')} USD. Missing samples mean unavailable, not zero.",
                    "FORECASTS",
                )
        else:
            raise ValueError("Unknown read-only tool")
        if snap.tasks_truncated and tool in {"tasks", "ai_usage"}:
            add(
                "bounded",
                "Task details are bounded to 100 recent/active tasks; this is not a complete historical census.",
                complete=False,
            )
        return result
