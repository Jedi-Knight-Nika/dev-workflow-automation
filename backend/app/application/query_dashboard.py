from dataclasses import replace
from datetime import UTC, datetime

from app.application.ports.dashboard_queries import (
    DashboardQueries,
    DashboardSnapshot,
    HealthCheckView,
)
from app.application.ports.telemetry import TelemetryCollector


class QueryDashboard:
    def __init__(self, queries: DashboardQueries, telemetry: TelemetryCollector) -> None:
        self._queries = queries
        self._telemetry = telemetry

    async def snapshot(self, period: str) -> DashboardSnapshot:
        if period not in {"today", "7d", "30d"}:
            raise ValueError("Dashboard period must be today, 7d, or 30d")
        dashboard = await self._queries.snapshot(period)
        telemetry = self._telemetry.snapshot()
        resource_status = (
            "CRITICAL"
            if telemetry.disk_percent >= 95 or telemetry.memory_percent >= 98
            else "DEGRADED"
            if telemetry.disk_percent >= 85
            or telemetry.memory_percent >= 90
            or telemetry.cpu_percent >= 95
            else "HEALTHY"
        )
        now = datetime.now(UTC)
        resource_health = HealthCheckView(
            "Host resources",
            resource_status,
            (
                f"CPU {telemetry.cpu_percent:.0f}% · RAM {telemetry.memory_percent:.0f}% "
                f"· disk {telemetry.disk_percent:.0f}%"
            ),
            now if resource_status == "HEALTHY" else None,
            now if resource_status != "HEALTHY" else None,
        )
        health = (*dashboard.health, resource_health)
        configured = tuple(item for item in health if item.status != "NOT_CONFIGURED")
        healthy = sum(item.status == "HEALTHY" for item in configured)
        status = (
            "CRITICAL"
            if any(item.status == "CRITICAL" for item in configured)
            else "DEGRADED"
            if any(item.status == "DEGRADED" for item in configured)
            else "HEALTHY"
        )
        return replace(
            dashboard,
            system_status=status,
            health_score=round(healthy / len(configured) * 100),
            health=health,
        )
