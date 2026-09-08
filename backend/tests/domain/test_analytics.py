from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.domain.efficiency import RunFact, TaskFact, quantile, run_totals, task_metrics
from app.analytics.domain.forecast import forecast

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def run(cost=Decimal(1), **changes):
    return replace(
        RunFact(
            "run",
            "task",
            "profile",
            "test",
            "model",
            "codex",
            "DEVELOPER",
            "DEVELOPER_TURN",
            "COMPLETED",
            NOW - timedelta(minutes=2),
            NOW - timedelta(minutes=1),
            cost,
            Decimal(2),
            100,
            20,
            80,
            None,
            10,
            True,
            30000,
        ),
        **changes,
    )


def task(identifier="task", **changes):
    return replace(
        TaskFact(
            identifier,
            "UI change",
            "team",
            "repo",
            "trello",
            100,
            "MERGED",
            NOW - timedelta(days=2),
            NOW - timedelta(days=1),
            [run()],
        ),
        **changes,
    )


def test_cost_unknown_and_token_subsets_are_not_double_counted():
    totals = run_totals([run(), run(None)])
    assert totals["known_cost_usd"] == "1"
    assert totals["cost_usd"] is None
    assert totals["unknown_cost_runs"] == 1
    assert totals["input_tokens"] == 200
    assert totals["output_tokens"] == 40  # reasoning is already included
    assert totals["cache_read_tokens"] == 160  # subset, not extra input
    assert totals["reserved_usd"] == "0"  # stopped runs no longer reserve


def test_provider_active_and_human_wait_are_separate():
    value = task(phases=[{"stage": "REVIEWING", "status": "WAITING_EXTERNAL", "seconds": 3600}])
    result = task_metrics(value)
    assert result["developer_active_seconds"] == 60
    assert result["human_or_external_wait_seconds"] == 3600


def test_forecast_has_no_future_leakage_and_needs_real_samples():
    target = task("target", created_at=NOW, completed_at=None, status="NEW", runs=[])
    history = [task(str(i)) for i in range(5)]
    future = task("future", completed_at=NOW + timedelta(days=1), runs=[run(Decimal(1000))])
    result = forecast(target, [*history, future], 5)
    assert result["sample_count"] == 5
    assert result["confidence"] == "LOW"
    assert result["estimate"]["cost_usd"]["estimate"] == 1
    assert result["estimate"]["peak_memory_bytes"]["estimate"] is None
    assert forecast(target, history[:2], 5)["confidence"] == "INSUFFICIENT"
    assert forecast(target, [], 5)["estimate"]["cost_usd"]["estimate"] is None


def test_quantiles_are_interpolated_and_empty_is_not_zero():
    assert quantile([], 0.5) is None
    assert quantile([1, 3], 0.5) == 2
    assert quantile([1, 3], 0.9) == 2.8
