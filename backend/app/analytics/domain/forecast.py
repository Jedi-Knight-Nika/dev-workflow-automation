"""No AI, no scheduler authority, no training leakage from future outcomes."""

from collections.abc import Callable
from typing import Any

from app.analytics.domain.efficiency import TaskFact, quantile, task_metrics

VERSION = "quantiles-v1"


def complexity(task: TaskFact) -> str:
    if task.estimate is not None:
        return "complex" if task.estimate >= 8 else "normal" if task.estimate >= 3 else "small"
    if task.description_length > 3000 or any(
        word in (task.title + " " + " ".join(task.labels)).lower()
        for word in ("migration", "architecture", "refactor", "multi-repo")
    ):
        return "complex"
    return "small" if task.description_length < 500 else "normal"


def identity(task: TaskFact) -> tuple[str | None, str | None]:
    run = next((r for r in task.runs if r.role == "DEVELOPER"), None)
    return (run.harness, run.model) if run else (task.planned_harness, task.planned_model)


def forecast(target: TaskFact, history: list[TaskFact], minimum: int) -> dict[str, Any]:
    # Started/completed tasks must not obtain a retroactively fabricated forecast.
    before = target.created_at
    eligible = [
        t
        for t in history
        if t.id != target.id
        and t.runs
        and t.status == "MERGED"
        and t.completed_at
        and t.completed_at < before
    ]
    harness, model = identity(target)
    predicates: list[tuple[str, Callable[[TaskFact], bool]]] = [
        (
            "repository/harness/model/complexity",
            lambda t: (
                bool(model)
                and t.repository_id == target.repository_id
                and identity(t) == (harness, model)
                and complexity(t) == complexity(target)
            ),
        ),
        (
            "repository/harness/model",
            lambda t: (
                bool(model)
                and t.repository_id == target.repository_id
                and identity(t) == (harness, model)
            ),
        ),
        (
            "team/harness/model",
            lambda t: (
                bool(model) and t.team_id == target.team_id and identity(t) == (harness, model)
            ),
        ),
        ("harness/model", lambda t: bool(model) and identity(t) == (harness, model)),
        ("team", lambda t: t.team_id == target.team_id),
        ("global", lambda t: True),
    ]
    selected, basis = eligible, "global"
    for name, predicate in predicates:
        group = [t for t in eligible if predicate(t)]
        if len(group) >= minimum:
            selected, basis = group, name
            break
    metrics = [task_metrics(t) for t in selected]
    estimates: dict[str, Any] = {}
    for key in (
        "cost_usd",
        "input_tokens",
        "output_tokens",
        "developer_active_seconds",
        "peak_memory_bytes",
        "engineering_seconds",
    ):
        values = [float(m[key]) for m in metrics if m[key] is not None]
        p50, p90 = quantile(values, 0.5), quantile(values, 0.9)
        estimates[key] = {
            "estimate": p50 if len(values) >= minimum else None,
            "range": {
                "p50": p50 if len(values) >= minimum else None,
                "p90": p90 if len(values) >= minimum else None,
                "p75": quantile(values, 0.75) if len(values) >= minimum else None,
                "low": min(values) if len(values) >= minimum else None,
                "high": max(values) if len(values) >= minimum else None,
            },
            "sample_count": len(values),
            "confidence": "INSUFFICIENT"
            if len(values) < minimum
            else "LOW"
            if len(values) < 20
            else "MEDIUM"
            if len(values) < 100
            else "HIGH",
        }
    return {
        "forecast_version": VERSION,
        "model_kind": "statistical-quantiles",
        "basis": basis,
        "sample_count": len(selected),
        "confidence": "INSUFFICIENT"
        if len(selected) < minimum
        else "LOW"
        if len(selected) < 20
        else "MEDIUM"
        if len(selected) < 100
        else "HIGH",
        "estimate": estimates,
        "range": {key: value["range"] for key, value in estimates.items()},
        "complexity": complexity(target),
        "advisory_only": True,
    }
