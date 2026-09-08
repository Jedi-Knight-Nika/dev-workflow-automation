"""Typed, bounded requests. Neither the browser nor domain supplies PromQL."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Metric(StrEnum):
    CPU = "cpu"
    MEMORY = "memory"
    MEMORY_LIMIT = "memory_limit"
    MEMORY_PEAK = "memory_peak"
    CPU_SECONDS = "cpu_seconds"
    THROTTLED_SECONDS = "throttled_seconds"
    NETWORK_RX = "network_rx"
    NETWORK_TX = "network_tx"
    BLOCK_READ = "block_read"
    BLOCK_WRITE = "block_write"
    PIDS = "pids"
    LAST_SEEN = "last_seen"
    CONTAINER_START = "container_start"
    NETWORK_RX_RATE = "network_rx_rate"
    NETWORK_TX_RATE = "network_tx_rate"
    BLOCK_READ_RATE = "block_read_rate"
    BLOCK_WRITE_RATE = "block_write_rate"
    THROTTLED_RATE = "throttled_rate"
    MEMORY_FAILURES = "memory_failures"
    HOST_CPU = "host_cpu"
    HOST_MEMORY = "host_memory"
    HOST_MEMORY_TOTAL = "host_memory_total"
    HOST_MEMORY_AVAILABLE = "host_memory_available"
    HOST_DISK = "host_disk"
    HOST_DISK_AVAILABLE = "host_disk_available"
    HOST_SWAP = "host_swap"
    HOST_LOAD1 = "host_load1"
    HOST_LOAD5 = "host_load5"
    HOST_LOAD15 = "host_load15"
    HOST_UPTIME = "host_uptime"
    HOST_LAST_SEEN = "host_last_seen"
    HOST_NETWORK_RX = "host_network_rx"
    HOST_NETWORK_TX = "host_network_tx"
    HOST_DISK_READ = "host_disk_read"
    HOST_DISK_WRITE = "host_disk_write"
    HOST_DISK_BUSY = "host_disk_busy"
    HOST_DISK_GROWTH = "host_disk_growth"
    HOST_NETWORK_ERRORS = "host_network_errors"
    HOST_NETWORK_DROPS = "host_network_drops"
    HOST_BOOT_TIME = "host_boot_time"
    HOST_FILE_DESCRIPTORS = "host_file_descriptors"
    PROBE = "probe"
    PROBE_RATIO = "probe_ratio"
    PROBE_SAMPLES = "probe_samples"
    TARGET_UP = "target_up"


@dataclass(frozen=True)
class MetricQuery:
    metric: Metric
    service: str | None = None
    container_id: str | None = None
    window_seconds: int = 86400

    def __post_init__(self) -> None:
        if not 30 <= self.window_seconds <= 31 * 86400:
            raise ValueError("Invalid aggregation window")
        if self.service and not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", self.service):
            raise ValueError("Invalid service identity")
        if self.container_id and not re.fullmatch(r"[a-f0-9]{64}", self.container_id):
            raise ValueError("Invalid container identity")


@dataclass(frozen=True)
class MetricRangeQuery:
    query: MetricQuery
    start: datetime
    end: datetime
    step: int = 30

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Timezone-aware range required")
        seconds = (self.end - self.start).total_seconds()
        if not 0 < seconds <= 31 * 86400 or not 10 <= self.step <= 86400:
            raise ValueError("Range must be positive, at most 31 days; step 10–86400 seconds")
        if seconds / self.step > 3000:
            raise ValueError("Increase step: at most 3000 points per series")


@dataclass(frozen=True)
class MetricSeries:
    labels: dict[str, str]
    samples: list[tuple[float, float | None]]


@dataclass(frozen=True)
class MetricResult:
    status: str
    series: list[MetricSeries] = field(default_factory=list)
    sampled_at: datetime | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ResourceSummary:
    sample_coverage_ratio: float | None
    metrics_complete: bool
    values: dict[str, float | None]
