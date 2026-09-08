from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.analytics.application.ports import AnalyticsFacts
from app.analytics.domain.accuracy import evaluate
from app.analytics.domain.efficiency import RunFact, quantile, run_totals, task_metrics
from app.analytics.domain.forecast import VERSION, forecast


class BuildDashboard:
    async def forecast_accuracy(self) -> dict[str, Any]:
        return evaluate(await self.facts.forecast_snapshots())

    def __init__(self, facts: AnalyticsFacts, *, forecasts_enabled: bool, minimum: int) -> None:
        self.facts, self.enabled, self.minimum = facts, forecasts_enabled, minimum

    async def dashboard(self, days: int, team_id: UUID | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        since = now - timedelta(days=days)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        tasks = await self.facts.tasks(min(since, now - timedelta(days=30), month_start), team_id)
        all_runs = [r for t in tasks for r in t.runs if r.started_at <= now]
        runs = [r for r in all_runs if r.started_at >= since]
        groups: dict[str, dict[str, list[RunFact]]] = {
            name: defaultdict(list)
            for name in ("models", "agents", "daily", "run_kinds", "repositories")
        }
        for task in tasks:
            for run in task.runs:
                if not since <= run.started_at <= now:
                    continue
                groups["models"][f"{run.provider}/{run.model}"].append(run)
                groups["agents"][run.profile_id or f"{run.role}:unattributed"].append(run)
                groups["daily"][run.started_at.date().isoformat()].append(run)
                groups["run_kinds"][run.run_kind].append(run)
                groups["repositories"][task.repository_id or "unattributed"].append(run)
        merged = [
            task_metrics(t)
            for t in tasks
            if t.status == "MERGED" and t.completed_at and since <= t.completed_at <= now
        ]
        complete = [t for t in merged if t["cost_complete"]]
        agents = []
        for key, selected in groups["agents"].items():
            # Attribute to each profile that actually had a Developer run; counts are
            # participation, not disjoint ownership when a task changed profiles.
            cohort_ids = {r.task_id for r in selected if r.role == "DEVELOPER"}
            cohort = [t for t in tasks if t.id in cohort_ids]
            terminal = [t for t in cohort if t.status in {"MERGED", "FAILED", "CANCELLED"}]
            successes = [task_metrics(t) for t in terminal if t.status == "MERGED"]
            costs = [float(t["cost_usd"]) for t in successes if t["cost_complete"]]
            durations = [
                t["developer_active_seconds"]
                for t in successes
                if t["developer_active_seconds"] is not None
            ]
            agents.append(
                {
                    "key": key,
                    "display_name": next((r.profile_name for r in selected if r.profile_name), key),
                    "teams": sorted({t.team_name or t.team_id or "Unassigned" for t in cohort}),
                    **run_totals(selected),
                    "tasks_merged": len(successes),
                    "terminal_tasks": len(terminal),
                    "success_rate": len(successes) / len(terminal) if terminal else None,
                    "median_cost_usd": quantile(costs, 0.5),
                    "p90_cost_usd": quantile(costs, 0.9),
                    "average_cost_usd": sum(costs) / len(costs) if costs else None,
                    "p90_developer_seconds": quantile(durations, 0.9),
                    "tokens_per_merged_task": sum(
                        t["input_tokens"] + t["output_tokens"] for t in successes
                    )
                    / len(successes)
                    if successes
                    and all(
                        t["input_tokens"] is not None and t["output_tokens"] is not None
                        for t in successes
                    )
                    else None,
                    "input_tokens_per_merged_task": sum(t["input_tokens"] for t in successes)
                    / len(successes)
                    if successes and all(t["input_tokens"] is not None for t in successes)
                    else None,
                    "output_tokens_per_merged_task": sum(t["output_tokens"] for t in successes)
                    / len(successes)
                    if successes and all(t["output_tokens"] is not None for t in successes)
                    else None,
                    "median_developer_seconds": quantile(durations, 0.5),
                    "human_intervention_rate": sum(
                        any(p["status"] == "WAITING_HUMAN" for p in t.phases) for t in cohort
                    )
                    / len(cohort)
                    if cohort
                    else None,
                    "review_fix_cycles_per_task": sum(t.review_cycles for t in cohort) / len(cohort)
                    if cohort
                    else None,
                    "models": sorted({r.model for r in selected}),
                    "harnesses": sorted({r.harness for r in selected if r.harness}),
                }
            )
        return {
            "sampled_at": now.isoformat(),
            "days": days,
            "team_id": str(team_id) if team_id else None,
            "totals": run_totals(runs),
            "month_totals": run_totals([r for r in all_runs if r.started_at >= month_start]),
            "local_runs": [
                r
                for t in tasks
                for r in t.local_runs
                if since <= datetime.fromisoformat(r["started_at"]) <= now
            ],
            "agents": agents,
            "period_costs": {
                str(window): run_totals(
                    [r for r in all_runs if r.started_at >= now - timedelta(days=window)]
                )
                for window in (1, 7, 30)
            },
            "repository_names": {
                t.repository_id: t.repository_name for t in tasks if t.repository_id
            },
            "reliability": {
                "provider_failures": sum(r.status == "FAILED" for r in runs),
                "rate_limit_failures": sum("rate" in (r.failure_code or "").lower() for r in runs),
                "validation_failures": sum(t.validation_failures for t in tasks),
            },
            **{
                name: [{"key": key, **run_totals(items)} for key, items in sorted(group.items())]
                for name, group in groups.items()
                if name != "agents"
            },
            "merged_tasks": len(merged),
            "complete_merged_tasks": len(complete),
            "excluded_incomplete_tasks": len(merged) - len(complete),
            "cost_per_merged_task_usd": str(
                sum((Decimal(t["cost_usd"]) for t in complete), Decimal(0)) / len(complete)
            )
            if complete
            else None,
            "basis": "AI cards: runs started in window. Merged efficiency: lifetime receipts of tasks merged in window. Agent success: participating Developer profiles; cohorts may overlap.",
        }

    async def task(self, task_id: UUID) -> dict[str, Any] | None:
        tasks = await self.facts.tasks(datetime(1970, 1, 1, tzinfo=UTC), task_id=task_id)
        if not tasks:
            return None
        task = tasks[0]
        return {
            **task_metrics(task),
            "runs": [asdict(r) for r in task.runs],
            "local_runs": task.local_runs,
            "phase_history": task.phases,
            "forecasts": await self.facts.forecast_snapshots(task_id),
        }

    async def forecast_task(self, task_id: UUID) -> dict[str, Any] | None:
        tasks = await self.facts.tasks(datetime(1970, 1, 1, tzinfo=UTC), task_id=task_id)
        if not tasks:
            return None
        snapshots = await self.facts.forecast_snapshots(task_id)
        if snapshots:
            return snapshots[0]
        if not self.enabled or tasks[0].runs:
            return {
                "forecast_version": VERSION,
                "estimate": None,
                "range": None,
                "sample_count": 0,
                "confidence": "UNAVAILABLE",
                "reason": "Forecasts disabled or no pre-execution snapshot",
            }
        history = await self.facts.tasks(datetime.now(UTC) - timedelta(days=365))
        return forecast(tasks[0], history, self.minimum)

    async def forecast_queue(self, team_id: UUID | None = None) -> dict[str, Any]:
        history = await self.facts.tasks(datetime.now(UTC) - timedelta(days=365))
        queued = [
            t
            for t in history
            if not t.runs
            and t.status in {"NEW", "ACTIVE"}
            and (team_id is None or t.team_id == str(team_id))
        ]
        items = [forecast(t, history, self.minimum) for t in queued] if self.enabled else []
        costs = [f["estimate"]["cost_usd"] for f in items]
        complete = self.enabled and all(c["estimate"] is not None for c in costs)
        dimensions: dict[str, Any] = {}
        for metric in (
            "input_tokens",
            "output_tokens",
            "developer_active_seconds",
            "engineering_seconds",
        ):
            values = [f["estimate"][metric] for f in items]
            ready = self.enabled and all(v["estimate"] is not None for v in values)
            dimensions[metric] = {
                "estimate": sum(v["estimate"] for v in values) if ready else None,
                "range": {
                    q: sum(v["range"][q] for v in values) if ready else None for q in ("p50", "p90")
                },
            }
        memory: dict[str, list[float]] = defaultdict(list)
        caps = {t.team_id: t.concurrency for t in queued}
        for task, item in zip(queued, items, strict=False):
            peak = item["estimate"]["peak_memory_bytes"]["range"]["p90"]
            if peak is not None:
                memory[task.team_id or "unassigned"].append(peak)
        memory_ready = self.enabled and sum(map(len, memory.values())) == len(queued)
        capacity = sum(caps.values()) if caps else 1
        return {
            "forecast_version": VERSION,
            "queued_tasks": len(queued),
            "sample_count": min((f["sample_count"] for f in items), default=0),
            "confidence": "LOW" if complete and items else "INSUFFICIENT",
            "estimate": sum(c["estimate"] for c in costs) if complete else None,
            "range": {
                "p50": sum(c["range"]["p50"] for c in costs) if complete else None,
                "p90": sum(c["range"]["p90"] for c in costs) if complete else None,
            },
            "basis": "Sum of per-task quantiles, not a calibrated joint queue percentile",
            "advisory_only": True,
            "metrics": dimensions,
            "predicted_peak_concurrent_memory_bytes": sum(
                sum(sorted(values, reverse=True)[: caps.get(team, 1)])
                for team, values in memory.items()
            )
            if memory_ready
            else None,
            "queue_drain_seconds": dimensions["developer_active_seconds"]["estimate"] / capacity
            if dimensions["developer_active_seconds"]["estimate"] is not None
            else None,
            "resource_basis": "Sum of each Team concurrency slot P90; drain time assumes full concurrency and excludes CI/reviewer delays",
        }

    async def forecast_period(self, days: int) -> dict[str, Any]:
        dashboard = await self.dashboard(30)
        # No implicit zero for days without a reliable collection baseline.
        daily = [float(r["cost_usd"]) for r in dashboard["daily"] if r["cost_complete"]]
        sufficient = (
            self.enabled
            and len(daily) >= self.minimum
            and not dashboard["totals"]["unknown_cost_runs"]
        )
        median, p90 = quantile(daily, 0.5), quantile(daily, 0.9)
        dimensions: dict[str, Any] = {}
        for key in ("input_tokens", "output_tokens", "runs"):
            values = [float(r[key]) for r in dashboard["daily"] if r[key] is not None]
            ready = self.enabled and len(values) >= self.minimum
            dimensions[key] = {
                "estimate": (quantile(values, 0.5) or 0) * days if ready else None,
                "range": {
                    q: (quantile(values, f) or 0) * days if ready else None
                    for q, f in (("p50", 0.5), ("p90", 0.9))
                },
            }
        completed_since = datetime.now(UTC) - timedelta(days=30)
        facts = await self.facts.tasks(completed_since)
        active_days: dict[str, list[float]] = defaultdict(list)
        for task in facts:
            if (
                task.status == "MERGED"
                and task.completed_at
                and task.completed_at >= completed_since
                and task.runs
            ):
                actual = task_metrics(task)["developer_active_seconds"]
                if actual is not None:
                    active_days[task.completed_at.date().isoformat()].append(actual / 3600)
        for key, values in (
            ("task_volume", [float(len(v)) for v in active_days.values()]),
            ("developer_compute_hours", [sum(v) for v in active_days.values()]),
        ):
            ready = self.enabled and len(values) >= self.minimum
            dimensions[key] = {
                "estimate": (quantile(values, 0.5) or 0) * days if ready else None,
                "range": {
                    q: (quantile(values, f) or 0) * days if ready else None
                    for q, f in (("p50", 0.5), ("p90", 0.9))
                },
            }
        return {
            "forecast_version": VERSION,
            "days": days,
            "sample_count": len(daily),
            "confidence": "LOW" if sufficient else "INSUFFICIENT",
            "estimate": median * days if sufficient and median is not None else None,
            "range": {
                "p50": median * days if sufficient and median is not None else None,
                "p90": p90 * days if sufficient and p90 is not None else None,
            },
            "basis": "Observed active-day spending quantiles × horizon; not a calibrated calendar-period percentile",
            "advisory_only": True,
            "metrics": dimensions,
        }
