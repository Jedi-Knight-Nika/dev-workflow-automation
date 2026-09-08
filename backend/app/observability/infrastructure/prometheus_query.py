"""Fixed PromQL templates with bounded IO, concurrency, cardinality and cache."""

import asyncio
import json
import math
from datetime import UTC, datetime
from time import monotonic

import httpx

from app.observability.domain.metrics import (
    Metric,
    MetricQuery,
    MetricRangeQuery,
    MetricResult,
    MetricSeries,
)

_HOST = {
    Metric.HOST_BOOT_TIME: "node_boot_time_seconds",
    Metric.HOST_DISK_BUSY: "max(rate(node_disk_io_time_seconds_total[2m])) * 100",
    Metric.HOST_DISK_GROWTH: '-sum(deriv(node_filesystem_avail_bytes{mountpoint="/"}[1h]))',
    Metric.HOST_NETWORK_ERRORS: "sum(rate(node_network_receive_errs_total[2m]) + rate(node_network_transmit_errs_total[2m]))",
    Metric.HOST_NETWORK_DROPS: "sum(rate(node_network_receive_drop_total[2m]) + rate(node_network_transmit_drop_total[2m]))",
    Metric.HOST_FILE_DESCRIPTORS: "node_filefd_allocated",
    Metric.HOST_LAST_SEEN: "timestamp(node_time_seconds)",
    Metric.HOST_CPU: '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[2m])))',
    Metric.HOST_MEMORY: "100 * (1 - sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes))",
    Metric.HOST_MEMORY_TOTAL: "sum(node_memory_MemTotal_bytes)",
    Metric.HOST_MEMORY_AVAILABLE: "sum(node_memory_MemAvailable_bytes)",
    Metric.HOST_DISK: '100 * (1 - sum(node_filesystem_avail_bytes{mountpoint="/"}) / sum(node_filesystem_size_bytes{mountpoint="/"}))',
    Metric.HOST_DISK_AVAILABLE: 'sum(node_filesystem_avail_bytes{mountpoint="/"})',
    Metric.HOST_SWAP: "sum(node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes)",
    Metric.HOST_LOAD1: "node_load1",
    Metric.HOST_LOAD5: "node_load5",
    Metric.HOST_LOAD15: "node_load15",
    Metric.HOST_UPTIME: "time() - node_boot_time_seconds",
    Metric.HOST_NETWORK_RX: 'sum(rate(node_network_receive_bytes_total{device!="lo"}[2m]))',
    Metric.HOST_NETWORK_TX: 'sum(rate(node_network_transmit_bytes_total{device!="lo"}[2m]))',
    Metric.HOST_DISK_READ: "sum(rate(node_disk_read_bytes_total[2m]))",
    Metric.HOST_DISK_WRITE: "sum(rate(node_disk_written_bytes_total[2m]))",
    Metric.PROBE: "probe_success",
    Metric.TARGET_UP: "up",
}
_CONTAINER = {
    Metric.CONTAINER_START: ("container_start_time_seconds", False),
    Metric.NETWORK_RX_RATE: ("container_network_receive_bytes_total", True),
    Metric.NETWORK_TX_RATE: ("container_network_transmit_bytes_total", True),
    Metric.BLOCK_READ_RATE: ("container_fs_reads_bytes_total", True),
    Metric.BLOCK_WRITE_RATE: ("container_fs_writes_bytes_total", True),
    Metric.THROTTLED_RATE: ("container_cpu_cfs_throttled_seconds_total", True),
    Metric.MEMORY_FAILURES: ("container_memory_failures_total", False),
    Metric.CPU: ("container_cpu_usage_seconds_total", True),
    Metric.CPU_SECONDS: ("container_cpu_usage_seconds_total", False),
    Metric.THROTTLED_SECONDS: ("container_cpu_cfs_throttled_seconds_total", False),
    Metric.MEMORY: ("container_memory_working_set_bytes", False),
    Metric.MEMORY_PEAK: ("container_memory_working_set_bytes", False),
    Metric.MEMORY_LIMIT: ("container_spec_memory_limit_bytes", False),
    Metric.NETWORK_RX: ("container_network_receive_bytes_total", False),
    Metric.NETWORK_TX: ("container_network_transmit_bytes_total", False),
    Metric.BLOCK_READ: ("container_fs_reads_bytes_total", False),
    Metric.BLOCK_WRITE: ("container_fs_writes_bytes_total", False),
    Metric.PIDS: ("container_processes", False),
    Metric.LAST_SEEN: ("container_last_seen", False),
}


def promql(query: MetricQuery) -> str:
    if query.metric == Metric.PROBE_RATIO:
        return f"avg_over_time(probe_success[{query.window_seconds}s])"
    if query.metric == Metric.PROBE_SAMPLES:
        return f"count_over_time(probe_success[{query.window_seconds}s])"
    if query.metric in _HOST:
        return _HOST[query.metric]
    name, rate = _CONTAINER[query.metric]
    labels = ['id!="/"', 'name!=""']
    if query.service:
        labels.append(f'container_label_com_docker_compose_service="{query.service}"')
    if query.container_id:
        labels.append(f'id=~".*{query.container_id}.*"')
    expression = name + "{" + ",".join(labels) + "}"
    if query.metric == Metric.MEMORY_PEAK:
        expression = f"max_over_time({expression}[24h])"
    if rate:
        expression = f"rate({expression}[2m])"
    return f"sum by (id,name,container_label_com_docker_compose_service) ({expression})"


class PrometheusQueryAdapter:
    def __init__(self, client: httpx.AsyncClient, *, enabled: bool, timeout: float = 3) -> None:
        self.client, self.enabled, self.timeout = client, enabled, timeout
        self.semaphore = asyncio.Semaphore(4)
        self.cache: dict[str, tuple[float, MetricResult]] = {}

    async def instant(self, query: MetricQuery) -> MetricResult:
        return await self._query("query", {"query": promql(query)})

    async def range(self, query: MetricRangeQuery) -> MetricResult:
        return await self._query(
            "query_range",
            {
                "query": promql(query.query),
                "start": str(query.start.timestamp()),
                "end": str(query.end.timestamp()),
                "step": str(query.step),
            },
        )

    async def _query(self, endpoint: str, params: dict[str, str]) -> MetricResult:
        if not self.enabled:
            return MetricResult("disabled", reason="Monitoring is disabled")
        key = endpoint + json.dumps(params, sort_keys=True)
        cached = self.cache.get(key)
        if cached and monotonic() - cached[0] < (4 if endpoint == "query" else 20):
            return cached[1]
        try:
            async with asyncio.timeout(self.timeout + 1), self.semaphore:  # noqa: SIM117 - bound acquisition and IO together
                async with self.client.stream(
                    "GET",
                    "/api/v1/" + endpoint,
                    params={
                        **params,
                        "timeout": f"{max(1, round(self.timeout * 1000))}ms",
                        "limit": "201",
                        "lookback_delta": "45s",
                    },
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for block in response.aiter_bytes():
                        body.extend(block)
                        if len(body) > 8 * 1024**2:
                            raise ValueError("Metric response exceeded bound")
            payload = json.loads(body)
            if (
                not isinstance(payload, dict)
                or payload.get("status") != "success"
                or payload.get("warnings")
            ):
                raise ValueError("Incomplete Prometheus response")
            rows = payload["data"]["result"]
            if not isinstance(rows, list) or len(rows) > 200:
                raise ValueError("Metric cardinality exceeded bound")
            series = []
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("metric"), dict):
                    raise TypeError("Invalid metric series")
                samples = row.get("values", [row["value"]] if "value" in row else [])
                if len(samples) > 3001:
                    raise ValueError("Metric samples exceeded bound")
                values = []
                for stamp, value in samples:
                    number = float(value)
                    values.append((float(stamp), number if math.isfinite(number) else None))
                # Never forward arbitrary exporter labels or secret-bearing target URLs.
                labels = {
                    k: str(v)[:255]
                    for k, v in row["metric"].items()
                    if k
                    in {
                        "id",
                        "name",
                        "container_label_com_docker_compose_service",
                        "job",
                        "service",
                    }
                }
                series.append(MetricSeries(labels, values))
            result = MetricResult(
                "available" if series else "unavailable",
                series,
                datetime.now(UTC),
                None if series else "No metric samples",
            )
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
            if cached and monotonic() - cached[0] < 60:
                return MetricResult(
                    "stale", cached[1].series, cached[1].sampled_at, "Monitoring unavailable"
                )
            result = MetricResult("unavailable", reason="Monitoring unavailable")
        if len(self.cache) >= 128:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = monotonic(), result
        return result
