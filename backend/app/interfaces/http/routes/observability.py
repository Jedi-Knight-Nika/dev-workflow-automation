from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from secrets import compare_digest
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.bootstrap.observability import (
    get_metrics_adapter,
    get_monitoring_admin,
    get_observability_queries,
    get_observability_store,
)
from app.interfaces.http.schemas.observability import (
    AvailabilityResponse,
    EventResponse,
    IncidentResponse,
    LiveResponse,
    MetricResponse,
    RunnerResponse,
    TaskResourcesResponse,
)
from app.observability.application.ports import (
    MetricsQueryPort,
    MonitoringAdministration,
    ObservabilityQueries,
    ObservabilityStore,
)
from app.observability.domain.metrics import Metric, MetricQuery, MetricRangeQuery
from app.platform.configuration.settings import get_settings

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/live", response_model=LiveResponse)
async def live(
    queries: ObservabilityQueries = Depends(get_observability_queries),
) -> dict[str, Any]:
    return await queries.live()


@router.get("/services/{service}/history", response_model=MetricResponse)
async def history(
    service: str,
    metric: Metric,
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
    step: int = Query(default=30, ge=10, le=86400),
    queries: ObservabilityQueries = Depends(get_observability_queries),
) -> dict[str, Any]:
    try:
        return asdict(
            await queries.history(
                MetricRangeQuery(MetricQuery(metric, service=service), start, end, step)
            )
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/runners/{runner_id}", response_model=RunnerResponse)
async def runner(
    runner_id: UUID, store: ObservabilityStore = Depends(get_observability_store)
) -> dict[str, Any]:
    result = await store.runner(runner_id)
    if result is None:
        raise HTTPException(404, "Runner not found")
    return result


@router.get("/runners/{runner_id}/history", response_model=MetricResponse)
async def runner_history(
    runner_id: UUID,
    metric: Metric = Metric.MEMORY,
    store: ObservabilityStore = Depends(get_observability_store),
    metrics: MetricsQueryPort = Depends(get_metrics_adapter),
) -> dict[str, Any]:
    binding = await store.runner(runner_id)
    if binding is None:
        raise HTTPException(404, "Runner not found")
    end = binding["stopped_at"] or datetime.now(UTC)
    start = max(binding["started_at"], end - timedelta(days=30))
    seconds = (end - start).total_seconds()
    if seconds <= 0:
        return {"status": "unavailable", "series": []}
    return asdict(
        await metrics.range(
            MetricRangeQuery(
                MetricQuery(metric, container_id=binding["container_id"]),
                start,
                end,
                max(10, int(seconds / 2999) + 1),
            )
        )
    )


@router.get("/tasks/{task_id}/resources", response_model=TaskResourcesResponse)
async def task_resources(
    task_id: UUID, store: ObservabilityStore = Depends(get_observability_store)
) -> dict[str, Any]:
    return {
        "task_id": str(task_id),
        "runners": await store.runners(task_id),
        "events": await store.task_events(task_id),
        "basis": "Collected runner lifetimes only. Historical tasks may have no resource data.",
    }


@router.get("/availability", response_model=AvailabilityResponse)
async def availability(
    days: int = Query(30, ge=1, le=30),
    queries: ObservabilityQueries = Depends(get_observability_queries),
) -> dict[str, Any]:
    return await queries.availability(days)


@router.get("/incidents", response_model=list[IncidentResponse])
async def incidents(
    days: int = Query(30, ge=1, le=90), store: ObservabilityStore = Depends(get_observability_store)
) -> list[dict[str, Any]]:
    return await store.incidents(days)


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
async def incident(
    incident_id: UUID, store: ObservabilityStore = Depends(get_observability_store)
) -> dict[str, Any]:
    found = await store.incidents(90, incident_id)
    if not found:
        raise HTTPException(404, "Incident not found")
    return found[0]


@router.get("/events", response_model=list[EventResponse])
async def events(
    days: int = Query(7, ge=1, le=30), store: ObservabilityStore = Depends(get_observability_store)
) -> list[dict[str, Any]]:
    return await store.events(days)


class Alert(BaseModel):
    status: str = Field(pattern="^(firing|resolved)$")
    fingerprint: str = Field(pattern="^[a-f0-9]{1,64}$")
    labels: dict[str, str]
    startsAt: datetime
    endsAt: datetime | None = None


class AlertBatch(BaseModel):
    alerts: list[Alert] = Field(max_length=100)


@router.post("/alerts")
async def alerts(
    body: AlertBatch,
    authorization: str = Header(default=""),
    store: ObservabilityStore = Depends(get_observability_store),
    admin: MonitoringAdministration = Depends(get_monitoring_admin),
) -> dict[str, int]:
    token = get_settings().observability_alert_token
    if not token or not compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "Invalid monitoring authorization")
    if not (await admin.read()).get("alertmanager_enabled", True):
        return {"accepted": 0}
    for alert in body.alerts:
        if alert.startsAt.tzinfo is None or (alert.endsAt and alert.endsAt.tzinfo is None):
            raise HTTPException(422, "Timezone-aware alert timestamps required")
        service = alert.labels.get("service", alert.labels.get("job", "system"))[:80]
        kind = alert.labels.get("alertname", "UNAVAILABLE")[:40]
        # Discard annotations, command lines, arbitrary labels and all alert text.
        await store.alert(
            f"{alert.fingerprint}:{alert.startsAt.isoformat()}",
            service,
            kind,
            "critical" if alert.labels.get("severity") == "critical" else "warning",
            alert.startsAt,
            alert.endsAt if alert.status == "resolved" else None,
        )
    return {"accepted": len(body.alerts)}


@router.get("/settings")
async def monitoring_settings(
    admin: MonitoringAdministration = Depends(get_monitoring_admin),
) -> dict[str, Any]:
    s = get_settings()
    values = {
        "enabled": s.observability_enabled,
        "retention_days": s.observability_retention_days,
        "retention_size": s.observability_retention_size,
        "refresh_seconds": s.observability_live_refresh_seconds,
        "cpu_warning": s.observability_cpu_warning,
        "ram_warning": s.observability_ram_warning,
        "disk_warning": s.observability_disk_warning,
        "queue_warning_seconds": s.observability_queue_warning_seconds,
        "forecasts_enabled": s.forecasts_enabled,
        "forecast_min_samples": s.forecast_min_samples,
        "alertmanager_enabled": bool(s.observability_alert_token),
        "deployment_managed": True,
        "monthly_budget_usd": None,
        "forecast_horizon_days": s.forecast_horizon_days,
    }
    values.update(await admin.read())
    values["monitoring_deployed"] = s.observability_enabled
    values["forecasts_deployed"] = s.forecasts_enabled
    values["retention_pending_restart"] = (
        values["retention_days"] != s.observability_retention_days
        or values["retention_size"] != s.observability_retention_size
    )
    return values


class MonitoringUpdate(BaseModel):
    enabled: bool
    retention_days: int = Field(30, ge=1, le=90)
    retention_size: str = Field("5GB", pattern=r"^[1-9][0-9]*(MB|GB|TB)$")
    refresh_seconds: int = Field(5, ge=5, le=60)
    cpu_warning: int = Field(90, ge=1, le=100)
    ram_warning: int = Field(85, ge=1, le=100)
    disk_warning: int = Field(85, ge=1, le=100)
    queue_warning_seconds: int = Field(900, ge=30, le=86400)
    forecasts_enabled: bool = False
    forecast_min_samples: int = Field(5, ge=3, le=100)
    forecast_horizon_days: int = Field(7, ge=1, le=30)
    alertmanager_enabled: bool = True
    monthly_budget_usd: float | None = Field(None, gt=0, allow_inf_nan=False)


@router.put("/settings")
async def update_monitoring_settings(
    body: MonitoringUpdate, admin: MonitoringAdministration = Depends(get_monitoring_admin)
) -> dict[str, Any]:
    await admin.save(body.model_dump())
    return await monitoring_settings(admin)
