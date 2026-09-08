from datetime import UTC, datetime, timedelta

import pytest

from app.observability.domain.metrics import Metric, MetricQuery, MetricRangeQuery
from app.observability.domain.resources import summarize
from app.observability.infrastructure.docker_events import event_identity


def test_queries_reject_injection_and_unbounded_ranges():
    with pytest.raises(ValueError):
        MetricQuery(Metric.CPU, service='backend"} or up')
    with pytest.raises(ValueError):
        MetricQuery(Metric.CPU, container_id="a" * 63)
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        MetricRangeQuery(MetricQuery(Metric.MEMORY), now - timedelta(days=30), now, 10)
    with pytest.raises(ValueError):
        MetricRangeQuery(MetricQuery(Metric.MEMORY), now.replace(tzinfo=None), now)


def test_missing_metrics_are_unknown_and_counter_resets_are_counted():
    result = summarize({}, 0, 100)
    assert result.sample_coverage_ratio is None
    assert not result.metrics_complete
    assert all(v is None for v in result.values.values())
    partial = summarize(
        {
            "cpu_seconds": [(10, 2), (20, 5), (30, 1), (40, 3)],
            "memory": [(10, 100), (20, 300)],
            "last_seen": [(10, 10), (20, 10), (30, 30)],
        },
        0,
        100,
    )
    assert partial.values["cpu_seconds"] == 6
    assert partial.values["max_memory_bytes"] == 300
    assert partial.sample_coverage_ratio == 0.15
    assert not partial.metrics_complete


def test_short_runner_is_not_falsely_complete():
    result = summarize({"last_seen": [(1, 1)], "memory": [(1, 0)]}, 0, 5)
    assert result.values["max_memory_bytes"] == 0
    assert result.sample_coverage_ratio == 0
    assert not result.metrics_complete


def test_event_identity_is_idempotent_and_drops_sensitive_metadata():
    raw = {
        "Action": "start",
        "timeNano": 1800000000000000000,
        "Actor": {
            "ID": "a" * 64,
            "Attributes": {
                "managed_by": "scheduler-v2",
                "task_id": "00000000-0000-0000-0000-000000000001",
                "name": "developer-test",
                "OPENAI_API_KEY": "secret",
                "command": "secret",
            },
        },
    }
    first = event_identity(raw, "host", "project")
    assert first == event_identity(raw, "host", "project")
    assert first and first["kind"] == "DEVELOPER"
    assert "secret" not in str(first)
    raw["Actor"]["Attributes"] = {"com.docker.compose.project": "unrelated"}
    assert event_identity(raw, "host", "project") is None
