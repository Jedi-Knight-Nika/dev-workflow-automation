from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.activity.application.ports import ActivityScope, ActivityWindow
from app.bootstrap.activity import get_activity_queries
from app.interfaces.http.routes.visualization import router, stream_messages
from app.platform.configuration.settings import get_settings


async def test_live_capacity_shares_the_delivered_cursor_and_stops_with_the_stream(monkeypatch):
    import json

    from app.interfaces.http.routes import visualization

    now = datetime.now(UTC)
    window = ActivityWindow(ActivityScope("task", str(uuid4())), now - timedelta(days=1), now)
    queries = AsyncMock()
    queries.events.return_value = {"events": [], "next_sequence": 42, "has_more": False}
    queries.projection_status.return_value = {"delayed": False}
    queries.coverage.return_value = {"counts": {}}
    queries.capacity.return_value = {
        "teams": [],
        "through_sequence": 42,
        "as_of": now,
        "truncated": False,
    }
    request = AsyncMock()
    request.is_disconnected.return_value = False
    sleep = AsyncMock()
    monkeypatch.setattr(visualization.asyncio, "sleep", sleep)
    stream = stream_messages(request, queries, window, 10)
    assert '"sequence":42' in await anext(stream)
    status = await anext(stream)
    assert json.loads(status.split("data: ")[1])["capacity"]["through_sequence"] == 42
    for _ in range(10):
        assert "event: cursor" in await anext(stream)
    assert "event: status" in await anext(stream)
    assert queries.capacity.await_count == 2
    assert queries.capacity.call_args.args[0].start == window.start
    assert queries.capacity.call_args.args[1] == 42
    await stream.aclose()
    assert sleep.await_count == 10


def test_http_rejects_invalid_ranges_scopes_and_unbounded_pages(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    queries = AsyncMock()
    queries.preflight.return_value = {"events": 0}
    app.dependency_overrides[get_activity_queries] = lambda: queries
    client = TestClient(app)
    assert (
        client.post("/visualization/preflight", json={"from": "2026-01-01T00:00:00"}).status_code
        == 422
    )
    assert client.get("/visualization/events?limit=100000").status_code == 422
    assert client.get("/visualization/events?scope_type=invalid").status_code == 422
    queries.preflight.assert_not_awaited()
    monkeypatch.setattr(get_settings(), "activity_enabled", False)
    assert client.get("/visualization/events").status_code == 503
    queries.events.assert_not_awaited()


async def test_live_backfill_resets_instead_of_skipping_a_changed_baseline():
    now = datetime.now(UTC)
    queries = AsyncMock()
    queries.events.return_value = {
        "events": [{"sequence": 12, "occurred_at": now - timedelta(days=2)}],
        "next_sequence": 12,
        "has_more": False,
    }
    request = AsyncMock()
    request.is_disconnected.return_value = False
    stream = stream_messages(
        request,
        queries,
        ActivityWindow(ActivityScope("task", str(uuid4())), now - timedelta(days=1), now),
        11,
    )
    assert "event: reset" in await anext(stream)
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


def test_viewer_telemetry_is_bounded_and_contains_no_arbitrary_context():
    from app.activity.infrastructure.monitoring import ActivityMonitoring
    from app.bootstrap.activity import get_activity_monitor

    app = FastAPI()
    app.include_router(router)
    monitor = ActivityMonitoring()
    app.dependency_overrides[get_activity_monitor] = lambda: monitor
    client = TestClient(app)
    assert (
        client.post(
            "/visualization/telemetry",
            json={"draws": 3, "render_ms": 12, "init_ms": 25, "reconnects": 1},
        ).status_code
        == 204
    )
    assert client.post("/visualization/telemetry", json={"task_id": "private"}).status_code == 422
    assert client.post("/visualization/telemetry", json={"draws": -1}).status_code == 422
    assert client.post("/visualization/telemetry", json={"worker_crashes": 101}).status_code == 422
    assert (
        client.post(
            "/visualization/telemetry",
            content='{"render_ms": "NaN"}',
            headers={"Content-Type": "application/json"},
        ).status_code
        == 422
    )
    metrics = monitor.render().decode()
    assert 'aew_activity_viewer_events_total{kind="draws"} 3.0' in metrics
    assert "private" not in metrics
