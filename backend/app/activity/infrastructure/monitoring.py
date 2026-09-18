"""Low-cardinality viewer metrics. No task IDs, text, or engineering events are recorded."""

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class ActivityMonitoring:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.latency = Histogram(
            "aew_activity_query_seconds",
            "Activity read duration",
            ["operation"],
            registry=self.registry,
        )
        self.errors = Counter(
            "aew_activity_query_errors_total",
            "Activity query failures",
            ["operation"],
            registry=self.registry,
        )
        self.returned = Counter(
            "aew_activity_events_returned_total",
            "Activity records returned",
            registry=self.registry,
        )
        self.streams = Gauge(
            "aew_activity_sse_connections", "Active viewer streams", registry=self.registry
        )
        self.resumes = Counter(
            "aew_activity_sse_resumes_total", "Resumed viewer streams", registry=self.registry
        )
        self.lag = Gauge(
            "aew_activity_projector_lag_seconds",
            "Time since the last successful projection, -1 if unknown",
            registry=self.registry,
        )
        self.client_counts = Counter(
            "aew_activity_viewer_events_total",
            "Browser viewer measurements",
            ["kind"],
            registry=self.registry,
        )
        self.lag.set(-1)
        self.enabled = Gauge(
            "aew_activity_projection_enabled",
            "Whether activity projection is configured",
            registry=self.registry,
        )
        self.init = Histogram(
            "aew_activity_renderer_init_seconds",
            "Renderer first frame latency",
            registry=self.registry,
        )
        self.render_time = Counter(
            "aew_activity_renderer_seconds_total",
            "Measured time drawing activity frames",
            registry=self.registry,
        )
        self.session_time = Counter(
            "aew_activity_viewer_seconds_total",
            "Observed viewer session duration",
            registry=self.registry,
        )

    @contextmanager
    def query(self, operation: str) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        except Exception:
            self.errors.labels(operation).inc()
            raise
        finally:
            self.latency.labels(operation).observe(perf_counter() - started)

    def stream_open(self, resumed: bool) -> None:
        self.streams.inc()
        if resumed:
            self.resumes.inc()

    def stream_close(self) -> None:
        self.streams.dec()

    def client_report(self, report: dict[str, float | int | None]) -> None:
        for name in (
            "draws",
            "reconnects",
            "worker_crashes",
            "graphics_failures",
            "gource_failures",
        ):
            self.client_counts.labels(name).inc(report.get(name) or 0)
        if report.get("init_ms") is not None:
            self.init.observe(float(report["init_ms"] or 0) / 1000)
        self.render_time.inc(float(report.get("render_ms") or 0) / 1000)
        self.session_time.inc(float(report.get("session_seconds") or 0))

    def render(self) -> bytes:
        return generate_latest(self.registry)


activity_monitoring = ActivityMonitoring()
