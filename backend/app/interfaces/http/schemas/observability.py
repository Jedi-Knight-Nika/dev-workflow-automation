"""Public response contracts. Domain query ports remain framework-independent."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExtensibleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class MetricSeriesResponse(BaseModel):
    labels: dict[str, str]
    samples: list[tuple[float, float | None]]


class MetricResponse(BaseModel):
    status: str
    series: list[MetricSeriesResponse] = Field(default_factory=list)
    sampled_at: datetime | None = None
    reason: str | None = None


class ServiceResourceResponse(ExtensibleResponse):
    id: str
    name: str | None = None
    service: str | None = None
    cpu: float | None = None
    memory: float | None = None
    memory_limit: float | None = None
    memory_peak: float | None = None
    network_rx_rate: float | None = None
    network_tx_rate: float | None = None
    block_read_rate: float | None = None
    block_write_rate: float | None = None
    restart_count: int | None = None
    exit_code: int | None = None
    uptime_seconds: float | None = None
    last_seen: float | None = None
    health: str | None = None
    state: str | None = None


class ResourceSummaryResponse(ExtensibleResponse):
    metrics_complete: bool
    sample_coverage_ratio: float | None
    values: dict[str, float | None]
    calculated_at: datetime


class RunnerResponse(ExtensibleResponse):
    runner_run_id: UUID
    container_id: str
    container_name: str
    task_id: UUID | None
    team_id: UUID | None
    agent_profile_id: UUID | None
    service_kind: str
    phase: str | None
    started_at: datetime
    stopped_at: datetime | None
    exit_code: int | None
    oom_killed: bool | None
    summary: ResourceSummaryResponse | None
    resources: ServiceResourceResponse | None = None


class EventResponse(ExtensibleResponse):
    id: UUID
    occurred_at: datetime
    container_id: str
    service_name: str
    event_type: str
    runner_run_id: UUID | None
    exit_code: int | None


class LiveResponse(ExtensibleResponse):
    status: str
    sampled_at: datetime | None = None
    data_freshness_seconds: float | None = None
    host: dict[str, float | None]
    services: list[ServiceResourceResponse]
    active_runners: list[RunnerResponse]
    events: list[EventResponse] = Field(default_factory=list)
    availability: MetricResponse | None = None
    targets: MetricResponse | None = None


class TaskResourcesResponse(BaseModel):
    task_id: UUID
    runners: list[RunnerResponse]
    events: list[EventResponse]
    basis: str


class IncidentResponse(ExtensibleResponse):
    id: UUID
    service_key: str
    kind: str
    severity: str
    opened_at: datetime
    closed_at: datetime | None
    source: str
    summary: str


class ProbeAvailabilityResponse(BaseModel):
    service: str
    uptime_ratio: float | None
    sample_coverage_ratio: float | None
    valid_samples: float | None
    samples: list[tuple[float, float | None]]


class AvailabilityResponse(ExtensibleResponse):
    status: str
    days: int
    services: list[ProbeAvailabilityResponse]
    basis: str
