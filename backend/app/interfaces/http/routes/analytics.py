from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.analytics.application.ports import AnalyticsQueries
from app.bootstrap.observability import get_analytics_queries
from app.interfaces.http.schemas.analytics import (
    AgentEfficiencyResponse,
    AnalyticsDashboardResponse,
    CostForecastResponse,
    ForecastAccuracyResponse,
    TaskAnalyticsResponse,
    TaskForecastResponse,
    UsageGroupResponse,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/forecast/accuracy", response_model=ForecastAccuracyResponse)
async def forecast_accuracy(
    queries: AnalyticsQueries = Depends(get_analytics_queries),
) -> dict[str, Any]:
    return await queries.forecast_accuracy()


@router.get("/ai", response_model=AnalyticsDashboardResponse)
async def ai(
    days: int = Query(30, ge=1, le=90),
    team_id: UUID | None = None,
    queries: AnalyticsQueries = Depends(get_analytics_queries),
) -> dict[str, Any]:
    return await queries.dashboard(days, team_id)


@router.get("/agents", response_model=list[AgentEfficiencyResponse])
async def agents(
    days: int = Query(30, ge=1, le=90),
    team_id: UUID | None = None,
    queries: AnalyticsQueries = Depends(get_analytics_queries),
) -> list[dict[str, Any]]:
    result = await queries.dashboard(days, team_id)
    return list(result["agents"])


@router.get("/models", response_model=list[UsageGroupResponse])
async def models(
    days: int = Query(30, ge=1, le=90), queries: AnalyticsQueries = Depends(get_analytics_queries)
) -> list[dict[str, Any]]:
    result = await queries.dashboard(days)
    return list(result["models"])


@router.get("/tasks/{task_id}", response_model=TaskAnalyticsResponse)
async def task(
    task_id: UUID, queries: AnalyticsQueries = Depends(get_analytics_queries)
) -> dict[str, Any]:
    result = await queries.task(task_id)
    if result is None:
        raise HTTPException(404, "Task not found")
    return result


@router.get("/forecast/tasks/{task_id}", response_model=TaskForecastResponse)
async def task_forecast(
    task_id: UUID, queries: AnalyticsQueries = Depends(get_analytics_queries)
) -> dict[str, Any]:
    result = await queries.forecast_task(task_id)
    if result is None:
        raise HTTPException(404, "Task not found")
    return result


@router.get("/forecast/queue", response_model=CostForecastResponse)
async def queue_forecast(
    team_id: UUID | None = None, queries: AnalyticsQueries = Depends(get_analytics_queries)
) -> dict[str, Any]:
    return await queries.forecast_queue(team_id)


@router.get("/forecast/period", response_model=CostForecastResponse)
async def period_forecast(
    days: int = Query(7, ge=1, le=30), queries: AnalyticsQueries = Depends(get_analytics_queries)
) -> dict[str, Any]:
    return await queries.forecast_period(days)
