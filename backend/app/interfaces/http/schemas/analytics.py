from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.interfaces.http.schemas.observability import ExtensibleResponse


class UsageTotalsResponse(ExtensibleResponse):
    known_cost_usd: str
    cost_usd: str | None
    cost_complete: bool
    unknown_cost_runs: int
    incomplete_usage_runs: int
    reserved_usd: str
    failed_spend_usd: str
    compaction_spend_usd: str
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    reasoning_tokens: int | None


class UsageGroupResponse(UsageTotalsResponse):
    key: str
    runs: int


class AgentEfficiencyResponse(UsageGroupResponse):
    display_name: str
    tasks_merged: int
    terminal_tasks: int
    success_rate: float | None
    median_cost_usd: float | None
    p90_cost_usd: float | None
    median_developer_seconds: float | None
    models: list[str]
    harnesses: list[str]


class AnalyticsDashboardResponse(ExtensibleResponse):
    sampled_at: datetime
    days: int
    totals: UsageTotalsResponse
    month_totals: UsageTotalsResponse
    period_costs: dict[str, UsageTotalsResponse]
    agents: list[AgentEfficiencyResponse]
    models: list[UsageGroupResponse]
    repositories: list[UsageGroupResponse]
    run_kinds: list[UsageGroupResponse]
    daily: list[UsageGroupResponse]
    merged_tasks: int
    complete_merged_tasks: int
    excluded_incomplete_tasks: int
    cost_per_merged_task_usd: str | None
    basis: str


class ForecastRangeResponse(ExtensibleResponse):
    p50: float | None
    p90: float | None


class ForecastMetricResponse(ExtensibleResponse):
    estimate: float | None
    range: ForecastRangeResponse


class CostForecastResponse(ExtensibleResponse):
    forecast_version: str
    confidence: str
    sample_count: int
    estimate: float | None
    range: ForecastRangeResponse | None
    metrics: dict[str, ForecastMetricResponse]
    basis: str


class TaskForecastResponse(ExtensibleResponse):
    forecast_version: str
    confidence: str
    sample_count: int
    estimate: dict[str, ForecastMetricResponse] | None
    range: dict[str, ForecastRangeResponse] | None


class RunUsageResponse(ExtensibleResponse):
    id: str
    model: str
    harness: str | None
    run_kind: str
    status: str
    cost: Decimal | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    reasoning_tokens: int | None
    started_at: datetime
    finished_at: datetime | None
    provider_duration_ms: int | None


class TaskAnalyticsResponse(UsageTotalsResponse):
    task_id: str
    title: str
    status: str
    runs: list[RunUsageResponse]
    forecasts: list[TaskForecastResponse]
    developer_active_seconds: float | None
    wall_seconds: float | None
    human_or_external_wait_seconds: float
    phases: dict[str, float]
    peak_memory_bytes: float | None
    warnings: list[str] = Field(default_factory=list)


class AccuracyMetricResponse(ExtensibleResponse):
    sample_count: int
    median_absolute_percentage_error: float | None
    p90_coverage: float | None
    mean_bias: float | None


class ForecastAccuracyResponse(ExtensibleResponse):
    metrics: dict[str, AccuracyMetricResponse]
    basis: str
