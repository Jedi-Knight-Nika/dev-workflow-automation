import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from app.observability.application.ports import MetricsQueryPort, ObservabilityStore
from app.observability.domain.metrics import Metric, MetricQuery, MetricRangeQuery, MetricResult


class QueryMetrics:
    def __init__(self, metrics: MetricsQueryPort, store: ObservabilityStore) -> None:
        self.metrics, self.store = metrics, store

    async def history(self, query: MetricRangeQuery) -> MetricResult:
        return await self.metrics.range(query)

    async def live(self) -> dict[str, Any]:
        host_keys = [m for m in Metric if m.value.startswith("host_")]
        service_keys = [
            Metric.CPU,
            Metric.MEMORY,
            Metric.MEMORY_LIMIT,
            Metric.MEMORY_PEAK,
            Metric.LAST_SEEN,
            Metric.CONTAINER_START,
            Metric.NETWORK_RX_RATE,
            Metric.NETWORK_TX_RATE,
            Metric.BLOCK_READ_RATE,
            Metric.BLOCK_WRITE_RATE,
            Metric.THROTTLED_RATE,
            Metric.PIDS,
            Metric.MEMORY_FAILURES,
        ]
        keys = host_keys + service_keys + [Metric.PROBE, Metric.TARGET_UP]
        results = dict(
            zip(
                keys,
                await asyncio.gather(*(self.metrics.instant(MetricQuery(k)) for k in keys)),
                strict=True,
            )
        )
        host: dict[str, float | None] = {}
        for key in host_keys:
            rows = results[key].series
            host[key.value] = rows[0].samples[-1][1] if rows and rows[0].samples else None
        services: dict[str, dict[str, Any]] = {}
        for key in service_keys:
            for row in results[key].series:
                identity = row.labels.get("id", "")
                if key == Metric.MEMORY_PEAK and identity not in services:
                    continue  # Historical peaks must not resurrect stopped containers.
                item = services.setdefault(
                    identity,
                    {
                        "id": identity,
                        "name": row.labels.get("name"),
                        "service": row.labels.get("container_label_com_docker_compose_service"),
                    },
                )
                item[key.value] = row.samples[-1][1] if row.samples else None
        now = datetime.now(UTC)
        runners, events, observations = await asyncio.gather(
            self.store.runners(active=True), self.store.events(7), self.store.containers()
        )
        for item in services.values():
            lifetime = [e for e in events if item["id"].endswith(e["container_id"])]
            item["restart_count"] = (
                sum(e["event_type"] == "restart" for e in lifetime) if lifetime else None
            )
            item["oom_count"] = (
                sum(e["event_type"] == "oom" for e in lifetime) if lifetime else None
            )
            item["state"] = next(
                (
                    e["event_type"]
                    for e in lifetime
                    if e["event_type"] in {"die", "start", "destroy", "restart"}
                ),
                "observed",
            )
            item["health"] = next(
                (
                    e["event_type"].removeprefix("health_status: ")
                    for e in lifetime
                    if e["event_type"].startswith("health_status: ")
                ),
                "unknown",
            )
            item["exit_code"] = next(
                (e["exit_code"] for e in lifetime if e["exit_code"] is not None), None
            )
            item["uptime_seconds"] = (
                max(0, now.timestamp() - item["container_start"])
                if item.get("container_start")
                else None
            )
            limit, memory = item.get("memory_limit"), item.get("memory")
            item["memory_ratio"] = memory / limit if memory is not None and limit else None
        for runner in runners:
            runner["resources"] = next(
                (s for s in services.values() if s["id"].endswith(runner["container_id"])), None
            )
            runner["wall_seconds"] = (now - runner["started_at"]).total_seconds()
        for observation in observations:
            observed_service = next(
                (s for s in services.values() if s["id"].endswith(observation["container_id"])),
                None,
            )
            if observed_service:
                observed_service.update(
                    {
                        k: v
                        for k, v in observation.items()
                        if k not in {"container_id", "observed_at"}
                    }
                )
            elif observation.get("state") != "running":
                services[observation["container_id"]] = {
                    "id": observation["container_id"],
                    **observation,
                }
        stamps = [r.sampled_at for r in results.values() if r.sampled_at]
        return {
            "sampled_at": min(stamps).isoformat() if stamps else None,
            "host": host,
            "services": list(services.values()),
            "active_runners": runners,
            "events": events[:40],
            "availability": asdict(results[Metric.PROBE]),
            "targets": asdict(results[Metric.TARGET_UP]),
            "data_freshness_seconds": (now - min(stamps)).total_seconds() if stamps else None,
            "status": "available"
            if all(r.status == "available" for r in results.values())
            else "partial"
            if stamps
            else "unavailable",
            "cpu_definition": "Container CPU is cores consumed; 100% = one logical core. Host CPU is normalized.",
        }

    async def availability(self, days: int) -> dict[str, Any]:
        end = datetime.now(UTC)
        # Graphs are downsampled; uptime uses every raw probe in the full window.
        step = max(30, (days * 86400 + 2999) // 3000)
        result = await self.metrics.range(
            MetricRangeQuery(MetricQuery(Metric.PROBE), end - timedelta(days=days), end, step)
        )
        ratios, counts = await asyncio.gather(
            self.metrics.instant(MetricQuery(Metric.PROBE_RATIO, window_seconds=days * 86400)),
            self.metrics.instant(MetricQuery(Metric.PROBE_SAMPLES, window_seconds=days * 86400)),
        )

        def by_service(values: MetricResult) -> dict[str, float | None]:
            return {
                row.labels.get("service", row.labels.get("job", "unknown")): row.samples[-1][1]
                for row in values.series
                if row.samples
            }

        ratio_values, count_values = by_service(ratios), by_service(counts)
        services = []
        for row in result.series:
            service = row.labels.get("service", row.labels.get("job", "unknown"))
            count = count_values.get(service)
            services.append(
                {
                    "service": service,
                    "uptime_ratio": ratio_values.get(service),
                    "sample_coverage_ratio": min(1, count / (days * 86400 / 30))
                    if count is not None
                    else None,
                    "valid_samples": count,
                    "samples": row.samples,
                }
            )
        return {
            "status": result.status,
            "days": days,
            "step_seconds": step,
            "services": services,
            "basis": "All successful raw probes / valid raw probes; graph downsampled, coverage based on 30-second scrapes; missing data is not downtime",
        }
