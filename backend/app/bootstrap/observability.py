"""Composition only: supporting services have their own tiny database pool."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.analytics.application.dashboard import BuildDashboard
from app.analytics.application.ports import AnalyticsQueries
from app.analytics.infrastructure.cache import CachedAnalyticsQueries
from app.analytics.infrastructure.persistence import SqlAnalyticsFacts
from app.observability.application.ports import (
    MonitoringAdministration,
    ObservabilityQueries,
    ObservabilityStore,
)
from app.observability.application.query_metrics import QueryMetrics
from app.observability.infrastructure.configuration import SqlMonitoringAdministration, preferences
from app.observability.infrastructure.persistence import SqlObservabilityStore
from app.observability.infrastructure.prometheus_query import PrometheusQueryAdapter
from app.platform.configuration.settings import get_settings


@lru_cache
def supporting_sessions() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        get_settings().database_url,
        pool_size=2,
        max_overflow=0,
        pool_timeout=2,
        pool_pre_ping=True,
        connect_args={"server_settings": {"statement_timeout": "3000", "lock_timeout": "500"}},
    )
    return async_sessionmaker(engine, expire_on_commit=False)


async def render_metrics() -> bytes:
    from app.observability.infrastructure.instrumentation import instrumentation

    return await instrumentation.render(supporting_sessions())


def observe_request(path: str, method: str, status: int, seconds: float) -> None:
    from app.observability.infrastructure.instrumentation import instrumentation

    instrumentation.observe(path, method, status, seconds)


@lru_cache
def get_metrics_adapter() -> PrometheusQueryAdapter:
    settings = get_settings()
    client = httpx.AsyncClient(
        base_url=settings.prometheus_url,
        timeout=settings.observability_timeout_seconds,
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
        follow_redirects=False,
    )
    return PrometheusQueryAdapter(
        client,
        enabled=settings.observability_enabled,
        timeout=settings.observability_timeout_seconds,
    )


def get_observability_store() -> ObservabilityStore:
    return SqlObservabilityStore(supporting_sessions())


def get_monitoring_admin() -> MonitoringAdministration:
    return SqlMonitoringAdministration(supporting_sessions())


async def get_observability_queries() -> ObservabilityQueries:
    values = await preferences(supporting_sessions())
    adapter = get_metrics_adapter()
    adapter.enabled = get_settings().observability_enabled and values.get("enabled", True)
    return QueryMetrics(adapter, get_observability_store())


async def get_analytics_queries() -> AnalyticsQueries:
    settings = get_settings()
    values = await preferences(supporting_sessions())
    return cached_analytics(
        settings.forecasts_enabled and values.get("forecasts_enabled", True),
        values.get("forecast_min_samples", settings.forecast_min_samples),
    )


@lru_cache(maxsize=8)
def cached_analytics(enabled: bool, minimum: int) -> AnalyticsQueries:
    return CachedAnalyticsQueries(
        BuildDashboard(
            SqlAnalyticsFacts(supporting_sessions()),
            forecasts_enabled=enabled,
            minimum=minimum,
        )
    )


@asynccontextmanager
async def supporting_controller() -> AsyncIterator[None]:
    settings = get_settings()
    if not settings.observability_enabled and not settings.forecasts_enabled:
        yield
        return
    from app.observability.infrastructure.docker_events import DockerEventsAdapter

    async with httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(uds=str(settings.docker_socket)),
        base_url="http://docker",
        timeout=3,
    ) as client:
        observer = DockerEventsAdapter(
            client,
            supporting_sessions(),
            get_metrics_adapter(),
            host=settings.observability_host_id,
            project=settings.observability_compose_project,
        )
        tasks = []
        if settings.observability_enabled:
            from app.bootstrap.metrics_server import serve_metrics

            tasks.append(asyncio.create_task(observer.run(), name="observability-independent"))
            tasks.append(asyncio.create_task(serve_metrics(), name="controller-metrics"))
        if settings.forecasts_enabled:
            from app.analytics.infrastructure.forecast_worker import run_forecasts

            tasks.append(
                asyncio.create_task(
                    run_forecasts(supporting_sessions(), settings.forecast_min_samples),
                    name="advisory-forecasts",
                )
            )
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
