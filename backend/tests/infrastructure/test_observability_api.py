from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.bootstrap.observability import (
    get_analytics_queries,
    get_observability_queries,
    get_observability_store,
)
from app.main import app


def test_new_apis_are_typed_and_old_health_survives_missing_monitoring():
    queries = AsyncMock()
    queries.live.return_value = {
        "status": "unavailable",
        "host": {},
        "services": [],
        "active_runners": [],
    }
    app.dependency_overrides[get_observability_queries] = lambda: queries
    app.dependency_overrides[get_analytics_queries] = lambda: AsyncMock()
    try:
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/api/observability/live").json()["status"] == "unavailable"
            assert (
                client.get(
                    "/api/observability/services/backend/history?metric=raw-promql"
                ).status_code
                == 422
            )
            assert client.get("/api/analytics/ai?days=100000").status_code == 422
            assert client.get("/api/observability/runners/not-a-uuid").status_code == 422
            assert client.get("/metrics").status_code in {401, 404}
    finally:
        app.dependency_overrides.clear()


def test_alert_ingestion_requires_secret_and_does_not_write_unauthorized():
    store = AsyncMock()
    app.dependency_overrides[get_observability_store] = lambda: store
    try:
        with TestClient(app) as client:
            assert client.post("/api/observability/alerts", json={"alerts": []}).status_code == 401
        store.alert.assert_not_called()
    finally:
        app.dependency_overrides.clear()
