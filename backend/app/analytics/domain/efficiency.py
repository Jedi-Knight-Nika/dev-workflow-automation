"""Receipt-based formulas shared by dashboard, drill-down and forecasts."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RunFact:
    id: str
    task_id: str
    profile_id: str | None
    provider: str
    model: str
    harness: str | None
    role: str
    run_kind: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    cost: Decimal | None
    reserved: Decimal | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    reasoning_tokens: int | None
    usage_complete: bool
    provider_duration_ms: int | None
    profile_name: str | None = None
    context_tokens: int | None = None
    first_edit_at: datetime | None = None
    failure_code: str | None = None
    long_context_tier: bool = False


@dataclass(frozen=True)
class TaskFact:
    id: str
    title: str
    team_id: str | None
    repository_id: str | None
    source: str
    description_length: int
    status: str
    created_at: datetime
    completed_at: datetime | None
    runs: list[RunFact] = field(default_factory=list)
    phases: list[dict[str, Any]] = field(default_factory=list)
    review_cycles: int = 0
    validation_failures: int = 0
    peak_memory: float | None = None
    planned_harness: str | None = None
    planned_model: str | None = None
    local_runs: list[dict[str, Any]] = field(default_factory=list)
    estimate: float | None = None
    labels: list[str] = field(default_factory=list)
    repository_name: str | None = None
    team_name: str | None = None
    concurrency: int = 1


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def run_totals(runs: list[RunFact]) -> dict[str, Any]:
    unknown = sum(r.cost is None for r in runs)
    known = sum((r.cost for r in runs if r.cost is not None), Decimal(0))
    tokens: dict[str, int | None] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
    ):
        values = [getattr(r, key) for r in runs]
        tokens[key] = sum(values) if all(v is not None for v in values) else None
    return {
        "runs": len(runs),
        "known_cost_usd": str(known),
        "cost_usd": str(known) if not unknown else None,
        "cost_complete": unknown == 0,
        "unknown_cost_runs": unknown,
        "incomplete_usage_runs": sum(not r.usage_complete for r in runs),
        "reserved_usd": str(
            sum((r.reserved or Decimal(0) for r in runs if r.status == "RUNNING"), Decimal(0))
        ),
        "failed_spend_usd": str(
            sum((r.cost for r in runs if r.status == "FAILED" and r.cost is not None), Decimal(0))
        ),
        "compaction_spend_usd": str(
            sum(
                (
                    r.cost
                    for r in runs
                    if r.run_kind == "DEVELOPER_COMPACTION" and r.cost is not None
                ),
                Decimal(0),
            )
        ),
        **tokens,
    }


def task_metrics(task: TaskFact) -> dict[str, Any]:
    totals = run_totals(task.runs)
    if not task.runs and task.status == "MERGED":
        totals.update(cost_complete=False, cost_usd=None, input_tokens=None, output_tokens=None)
    durations: dict[str, float] = {}
    human_wait = 0.0
    review_or_human_wait = 0.0
    wait_by_reason: dict[str, float] = {}
    for phase in task.phases:
        if phase["seconds"] is not None:
            key = f"{phase['stage']}:{phase['status']}"
            durations[key] = durations.get(key, 0) + phase["seconds"]
            if phase["status"] in {"WAITING_HUMAN", "WAITING_EXTERNAL"}:
                human_wait += phase["seconds"]
                reason = phase.get("wait_reason", "UNKNOWN")
                wait_by_reason[reason] = wait_by_reason.get(reason, 0) + phase["seconds"]
                if phase["status"] == "WAITING_HUMAN" or reason in {
                    "GITHUB_REVIEW",
                    "APPROVAL_REQUIRED",
                }:
                    review_or_human_wait += phase["seconds"]
    active = [r for r in task.runs if r.role == "DEVELOPER"]
    active_seconds = sum(
        (r.finished_at - r.started_at).total_seconds() for r in active if r.finished_at
    )
    warnings = []
    if sum(r.input_tokens or 0 for r in active) >= 200000:
        warnings.append("context_growth_warning")
    if len(active) > 5:
        warnings.append("high_turn_count")
    if any(
        (r.cache_read_tokens or 0) > 100000
        and (r.cache_read_tokens or 0) > (r.input_tokens or 0) * 0.8
        for r in active
    ):
        warnings.append("high_cache_read_cost")
    edits = [r.first_edit_at for r in active if r.first_edit_at]
    first_edit = min(edits) if edits else None
    if (
        first_edit
        and sum(
            r.input_tokens or 0 for r in active if r.finished_at and r.finished_at <= first_edit
        )
        > 100000
    ):
        warnings.append("high_tokens_before_first_edit")
    if any(r.long_context_tier for r in active):
        warnings.append("unexpected_long_context_tier")
    if Decimal(totals["failed_spend_usd"]) > Decimal(totals["known_cost_usd"]) / 2 and active:
        warnings.append("high_failed_spend")
    return {
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "team_id": task.team_id,
        "repository_id": task.repository_id,
        **totals,
        "developer_active_seconds": active_seconds if all(r.finished_at for r in active) else None,
        "wall_seconds": (task.completed_at - task.created_at).total_seconds()
        if task.completed_at
        else None,
        "human_or_external_wait_seconds": human_wait,
        "wait_seconds_by_reason": wait_by_reason,
        "provider_active_seconds": sum(
            r.provider_duration_ms for r in task.runs if r.provider_duration_ms is not None
        )
        / 1000
        if all(r.provider_duration_ms is not None for r in task.runs)
        else None,
        "provider_wait_seconds": sum(
            wait_by_reason.get(reason, 0) for reason in ("PROVIDER_RATE_LIMIT", "PROVIDER_OUTAGE")
        )
        if task.phases
        else None,
        "human_review_wait_seconds": review_or_human_wait,
        "engineering_seconds": max(
            0, (task.completed_at - task.created_at).total_seconds() - review_or_human_wait
        )
        if task.completed_at
        else None,
        "phase_seconds": {
            stage.lower() + "_seconds": sum(
                v for k, v in durations.items() if k.startswith(stage + ":") and "WAITING" not in k
            )
            for stage in (
                "INTAKE",
                "DEVELOPING",
                "VALIDATING",
                "PUBLISHING",
                "REVIEWING",
                "FIXING",
                "MERGING",
            )
        },
        "phases": durations,
        "developer_turns": sum(r.run_kind == "DEVELOPER_TURN" for r in active),
        "compactions": sum(r.run_kind == "DEVELOPER_COMPACTION" for r in active),
        "review_cycles": task.review_cycles,
        "validation_failures": task.validation_failures,
        "peak_memory_bytes": task.peak_memory,
        "warnings": warnings,
        "time_to_first_edit_seconds": (
            first_edit - min(r.started_at for r in active)
        ).total_seconds()
        if first_edit
        else None,
        "provider_failures": sum(r.status == "FAILED" for r in task.runs),
        "rate_limit_failures": sum("rate" in (r.failure_code or "").lower() for r in task.runs),
    }
