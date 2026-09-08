from typing import Any

from app.analytics.domain.efficiency import quantile


def evaluate(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {}
    for metric in (
        "cost_usd",
        "input_tokens",
        "output_tokens",
        "developer_active_seconds",
        "peak_memory_bytes",
    ):
        pairs = []
        for snapshot in snapshots:
            estimate = (snapshot.get("estimate") or {}).get(metric) or {}
            actual = (snapshot.get("actuals") or {}).get(metric)
            p50, p90 = estimate.get("estimate"), (estimate.get("range") or {}).get("p90")
            if actual is not None and p50 is not None and p90 is not None:
                pairs.append((float(p50), float(p90), float(actual)))
        percentages = [abs(p50 - actual) / actual for p50, _, actual in pairs if actual > 0]
        metrics[metric] = {
            "sample_count": len(pairs),
            "median_absolute_percentage_error": quantile(percentages, 0.5),
            "percentage_error_sample_count": len(percentages),
            "p90_coverage": sum(actual <= p90 for _, p90, actual in pairs) / len(pairs)
            if pairs
            else None,
            "mean_bias": sum(p50 - actual for p50, _, actual in pairs) / len(pairs)
            if pairs
            else None,
        }
    return {
        "metrics": metrics,
        "basis": "Original pre-execution forecasts vs separately finalized actuals; zero actuals excluded from percentage errors",
    }
