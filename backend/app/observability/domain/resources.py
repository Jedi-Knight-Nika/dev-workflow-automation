from itertools import pairwise
from statistics import mean

from app.observability.domain.metrics import ResourceSummary


def summarize(
    samples: dict[str, list[tuple[float, float | None]]],
    start: float,
    end: float,
    scrape_seconds: int = 10,
) -> ResourceSummary:
    """Coverage uses exporter sample timestamps, not interpolated range points.

    Counter deltas include resets but do not extrapolate unobserved lifetime edges.
    Such deltas are lower bounds when coverage is incomplete.
    """
    observed = sorted(
        {
            value
            for _, value in samples.get("last_seen", [])
            if value is not None and start <= value <= end
        }
    )
    duration = end - start
    covered = sum(min(b - a, scrape_seconds * 1.5) for a, b in pairwise(observed))
    coverage = min(1, covered / duration) if duration > 0 and observed else None
    values: dict[str, float | None] = {}
    for source, target in {
        "cpu_seconds": "cpu_seconds",
        "throttled_seconds": "cpu_throttled_seconds",
        "network_rx": "network_rx_bytes",
        "network_tx": "network_tx_bytes",
        "block_read": "block_read_bytes",
        "block_write": "block_write_bytes",
    }.items():
        raw = [v for at, v in samples.get(source, []) if start <= at <= end and v is not None]
        values[target] = (
            sum(b - a if b >= a else b for a, b in pairwise(raw)) if len(raw) >= 2 else None
        )
    memory = sorted(
        v for at, v in samples.get("memory", []) if start <= at <= end and v is not None
    )
    values.update(
        {
            "avg_memory_bytes": mean(memory) if memory else None,
            "max_memory_bytes": max(memory) if memory else None,
            "p95_memory_bytes": memory[min(len(memory) - 1, int(len(memory) * 0.95))]
            if memory
            else None,
        }
    )
    pids = [v for _, v in samples.get("pids", []) if v is not None]
    values["max_pids"] = max(pids) if pids else None
    complete = (
        coverage is not None and coverage >= 0.9 and all(v is not None for v in values.values())
    )
    return ResourceSummary(coverage, complete, values)
