from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ActiveWorkerView:
    job_id: str
    task_id: str
    task_label: str
    team_id: str | None
    team_name: str | None
    agent_name: str | None
    role: str
    provider: str | None
    model: str | None
    started_at: datetime | None
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class QueueItemView:
    job_id: str
    task_id: str
    task_label: str
    team_id: str | None
    team_name: str | None
    role: str
    action: str
    priority: int
    state: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TeamActivityView:
    team_id: str
    name: str
    status: str
    current_task_id: str | None
    current_task_label: str | None
    agent_name: str | None
    role: str | None
    provider: str | None
    model: str | None
    queued_jobs: int
    open_pull_requests: int
    ready_to_merge: int
    tokens: int


@dataclass(frozen=True, slots=True)
class ActivityEventView:
    id: str
    timestamp: datetime
    team_id: str | None
    team_name: str | None
    task_id: str
    task_label: str
    source: str
    severity: str
    event_type: str
    summary: str


@dataclass(frozen=True, slots=True)
class UsageBucketView:
    key: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float | None


@dataclass(frozen=True, slots=True)
class TimeBucketView:
    period: str
    completed: int = 0
    failed: int = 0
    human_assisted: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class HealthCheckView:
    name: str
    status: str
    message: str
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    period: str
    generated_at: datetime
    system_status: str
    health_score: int
    active_tasks: int
    queued_jobs: int
    ready_to_merge: int
    needs_human: int
    completed: int
    failed: int
    tokens: int
    estimated_cost: float | None
    autonomy_rate: float | None
    active_worker: ActiveWorkerView | None
    queue: tuple[QueueItemView, ...]
    teams: tuple[TeamActivityView, ...]
    recent_events: tuple[ActivityEventView, ...]
    usage_by_role: tuple[UsageBucketView, ...]
    usage_by_provider: tuple[UsageBucketView, ...]
    usage_by_team: tuple[UsageBucketView, ...]
    throughput: tuple[TimeBucketView, ...]
    token_history: tuple[TimeBucketView, ...]
    health: tuple[HealthCheckView, ...]


class DashboardQueries(Protocol):
    async def snapshot(self, period: str) -> DashboardSnapshot: ...
