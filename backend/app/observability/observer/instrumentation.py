"""Low-cardinality Observer meters, separate from paid AI/Team accounting."""

from prometheus_client import Counter, Histogram

from app.observability.infrastructure.instrumentation import instrumentation

COUNTERS = {
    name: Counter(
        "observer_" + name, "Observer " + name.replace("_", " "), registry=instrumentation.registry
    )
    for name in (
        "questions_total",
        "briefings_total",
        "model_requests_total",
        "model_failures_total",
        "tool_calls_total",
        "tool_failures_total",
        "deterministic_fallback_total",
        "capacity_denied_total",
        "model_prompt_tokens_total",
        "model_output_tokens_total",
    )
}
DURATIONS = {
    name: Histogram(
        "observer_" + name, "Observer " + name.replace("_", " "), registry=instrumentation.registry
    )
    for name in (
        "question_duration_seconds",
        "anomaly_detection_duration_seconds",
    )
}


def record(name: str, value: float = 1) -> None:
    if name in COUNTERS:
        COUNTERS[name].inc(value)
    elif name in DURATIONS:
        DURATIONS[name].observe(value)
