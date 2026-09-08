"""Low-cardinality operational mirrors. PostgreSQL remains billing truth."""

import asyncio
from collections.abc import Iterable
from time import monotonic

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.observability.infrastructure.models import MonitoringConfiguration
from app.platform.configuration.settings import get_settings


class OperationalCollector:
    def __init__(self) -> None:
        self.values: list[Metric] = []

    def collect(self) -> Iterable[Metric]:
        return iter(self.values)


class Instrumentation:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "aew_http_requests_total",
            "HTTP requests",
            ("route_group", "method", "status_class"),
            registry=self.registry,
        )
        self.latency = Histogram(
            "aew_http_request_duration_seconds",
            "HTTP latency",
            ("route_group", "method"),
            registry=self.registry,
        )
        self.mirror = OperationalCollector()
        self.registry.register(self.mirror)
        self.lock = asyncio.Lock()
        self.refreshed = 0.0

    def observe(self, path: str, method: str, status: int, seconds: float) -> None:
        if path == "/metrics":
            return
        parts = path.strip("/").split("/")
        group = parts[1] if len(parts) > 1 and parts[0] == "api" else parts[0]
        if group not in {
            "tasks",
            "teams",
            "repositories",
            "integrations",
            "settings",
            "dashboard",
            "observability",
            "observer",
            "analytics",
            "health",
            "webhooks",
            "events",
        }:
            group = "other"
        method = (
            method
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
            else "OTHER"
        )
        self.requests.labels(group, method, f"{status // 100}xx").inc()
        self.latency.labels(group, method).observe(seconds)

    async def render(self, sessions: async_sessionmaker[AsyncSession]) -> bytes:
        async with self.lock:
            if monotonic() - self.refreshed >= 15:
                try:
                    async with asyncio.timeout(4), sessions() as session:
                        values: list[Metric] = []
                        configuration = await session.get(MonitoringConfiguration, "default")
                        prefs = configuration.values if configuration else {}
                        defaults = get_settings()
                        for key in (
                            "cpu_warning",
                            "ram_warning",
                            "disk_warning",
                            "queue_warning_seconds",
                        ):
                            values.append(
                                GaugeMetricFamily(
                                    "aew_monitoring_" + key,
                                    "Configured operator warning",
                                    value=float(
                                        prefs.get(key, getattr(defaults, "observability_" + key))
                                    ),
                                )
                            )
                        for name, sql in (
                            (
                                "aew_scheduler_queue_depth",
                                "SELECT count(*) FROM jobs WHERE state='QUEUED'",
                            ),
                            (
                                "aew_scheduler_oldest_queued_seconds",
                                "SELECT coalesce(extract(epoch from now()-min(created_at)),0) FROM jobs WHERE state='QUEUED'",
                            ),
                            (
                                "aew_active_developer_runners",
                                "SELECT count(*) FROM jobs WHERE state='RUNNING' AND action='DEVELOPER_TURN'",
                            ),
                            (
                                "aew_active_validation_runners",
                                "SELECT count(*) FROM jobs WHERE state='RUNNING' AND action='RUN_VALIDATION'",
                            ),
                        ):
                            values.append(
                                GaugeMetricFamily(
                                    name, name, value=float(await session.scalar(text(sql)) or 0)
                                )
                            )
                        stages = GaugeMetricFamily(
                            "aew_tasks_by_stage", "Tasks by stage", labels=["stage"]
                        )
                        for stage, count in await session.execute(
                            text(
                                "SELECT stage,count(*) FROM tasks WHERE archived_at IS NULL GROUP BY stage"
                            )
                        ):
                            stages.add_metric([stage], count)
                        values.append(stages)
                        ai = CounterMetricFamily(
                            "aew_ai_runs",
                            "Persisted AI runs",
                            labels=["provider", "model", "harness", "run_kind", "result"],
                        )
                        rows = (
                            await session.execute(
                                text("""SELECT provider, model, coalesce(harness,'api'),
                            CASE WHEN prompt_version LIKE '%compaction%' THEN 'DEVELOPER_COMPACTION'
                                 WHEN role_kind='DEVELOPER' THEN 'DEVELOPER_TURN'
                                 WHEN role_kind='INTERPRETER' THEN 'INTERPRETER_CLOUD' ELSE role_kind END,
                            status, count(*) FROM ai_runs GROUP BY 1,2,3,4,5 LIMIT 201""")
                            )
                        ).all()
                        if len(rows) > 200:
                            raise ValueError("AI metric cardinality exceeded")
                        for provider, model, harness, kind, status, count in rows:
                            ai.add_metric([provider, model, harness, kind, status], count)
                        values.append(ai)
                        cost = CounterMetricFamily(
                            "aew_ai_cost_usd",
                            "Known receipt cost only",
                            labels=["provider", "model"],
                        )
                        tokens = CounterMetricFamily(
                            "aew_ai_tokens",
                            "Input/output and cached subset",
                            labels=["provider", "model", "token_kind"],
                        )
                        for provider, model, usd, inputs, outputs, cached in await session.execute(
                            text("""SELECT provider, model,
                            sum(coalesce(provider_cost_usd,calculated_cost_usd)),sum(input_tokens),sum(output_tokens),sum(cache_read_tokens)
                            FROM ai_runs GROUP BY 1,2 LIMIT 200""")
                        ):
                            if usd is not None:
                                cost.add_metric([provider, model], float(usd))
                            for label, value in (
                                ("input", inputs),
                                ("output", outputs),
                                ("cached_input", cached),
                            ):
                                if value is not None:
                                    tokens.add_metric([provider, model, label], value)
                        values.extend(
                            [
                                cost,
                                tokens,
                                GaugeMetricFamily(
                                    "aew_metrics_database_available", "DB mirror available", value=1
                                ),
                            ]
                        )
                        for name, labels, sql in (
                            (
                                "aew_webhook_deliveries",
                                ["source", "result"],
                                "SELECT provider,status,count(*) FROM webhook_deliveries GROUP BY 1,2 LIMIT 200",
                            ),
                            (
                                "aew_provider_failures",
                                ["provider", "error_class"],
                                "SELECT provider,CASE WHEN failure_code ILIKE '%rate%' THEN 'rate_limit' WHEN failure_code ILIKE '%timeout%' THEN 'timeout' ELSE 'other' END,count(*) FROM ai_runs WHERE status='FAILED' GROUP BY 1,2 LIMIT 200",
                            ),
                            (
                                "aew_provider_rate_limits",
                                ["provider"],
                                "SELECT provider,count(*) FROM ai_runs WHERE failure_code ILIKE '%rate%' GROUP BY 1 LIMIT 200",
                            ),
                            (
                                "aew_task_transitions",
                                ["from_stage", "to_stage"],
                                "SELECT previous,stage,count(*) FROM (SELECT stage,lag(stage) OVER(PARTITION BY task_id ORDER BY started_at) previous FROM task_phase_runs) phases WHERE previous IS NOT NULL GROUP BY 1,2 LIMIT 200",
                            ),
                        ):
                            counter = CounterMetricFamily(name, name, labels=labels)
                            for row in await session.execute(text(sql)):
                                counter.add_metric([str(v) for v in row[:-1]], row[-1])
                            values.append(counter)
                        for name, sql in (
                            (
                                "aew_worker_heartbeat_age_seconds",
                                "SELECT extract(epoch from now()-max(last_heartbeat)) FROM worker_nodes WHERE stopped_at IS NULL",
                            ),
                            (
                                "aew_unknown_stopped_ai_cost_runs",
                                "SELECT count(*) FROM ai_runs WHERE status!='RUNNING' AND provider_cost_usd IS NULL AND calculated_cost_usd IS NULL",
                            ),
                            (
                                "aew_runner_oom_events",
                                "SELECT count(*) FROM infrastructure_events WHERE event_type='oom'",
                            ),
                            (
                                "aew_container_restarts",
                                "SELECT count(*) FROM infrastructure_events WHERE event_type='restart'",
                            ),
                        ):
                            value = await session.scalar(text(sql))
                            if value is not None:
                                values.append(GaugeMetricFamily(name, name, value=float(value)))
                        self.mirror.values = values
                except Exception:  # noqa: BLE001 - isolate telemetry failures
                    self.mirror.values = [
                        GaugeMetricFamily(
                            "aew_metrics_database_available", "DB mirror available", value=0
                        )
                    ]
                self.refreshed = monotonic()
        return generate_latest(self.registry)


instrumentation = Instrumentation()
