"""One product API and stable, bounded operational route labels."""

import warnings

from app.main import app
from app.observability.infrastructure.instrumentation import Instrumentation


def test_product_routes_have_one_canonical_mount_without_hidden_aliases():
    # Included routers are lazy in the pinned FastAPI; use its public schema contract.
    app.openapi_schema = None
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        schema = app.openapi()
    paths = set(schema["paths"])
    operations = [op["operationId"] for path in schema["paths"].values() for op in path.values()]
    assert len(operations) == len(set(operations))
    assert {
        "/api/tasks",
        "/api/teams",
        "/api/tasks/{task_id}/session",
        "/api/tasks/{task_id}/token-efficiency",
        "/api/observability/live",
        "/api/statistics",
    } <= paths
    assert all(
        path == "/" or path == "/metrics" or path.startswith(("/api/", "/health/", "/webhooks/"))
        for path in paths
    )


def test_canonical_route_metrics_do_not_label_task_ids_or_unknown_paths():
    metrics = Instrumentation()
    metrics.observe("/api/tasks/private-task-id/session", "GET", 200, 0.1)
    metrics.observe("/api/untrusted-label", "CUSTOM", 404, 0.1)
    samples = [
        s for m in metrics.requests.collect() for s in m.samples if s.name.endswith("_total")
    ]
    assert {s.labels["route_group"] for s in samples} == {"tasks", "other"}
    assert {s.labels["method"] for s in samples} == {"GET", "OTHER"}
