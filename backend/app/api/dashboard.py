from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.application.ports.dashboard_queries import DashboardQueries
from app.application.ports.telemetry import TelemetryCollector
from app.application.query_dashboard import QueryDashboard
from app.bootstrap.dependencies import get_dashboard_queries, get_telemetry_collector

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def dashboard_summary(
    queries: Annotated[DashboardQueries, Depends(get_dashboard_queries)],
    collector: Annotated[TelemetryCollector, Depends(get_telemetry_collector)],
    period: Annotated[str, Query(pattern="^(today|7d|30d)$")] = "today",
) -> dict[str, Any]:
    try:
        return asdict(await QueryDashboard(queries, collector).snapshot(period))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/telemetry")
async def dashboard_telemetry(
    collector: Annotated[TelemetryCollector, Depends(get_telemetry_collector)],
) -> dict[str, Any]:
    return asdict(collector.snapshot())
