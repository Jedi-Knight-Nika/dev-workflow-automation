import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.domain.agents import AgentRole
from app.domain.operational_states import IndexStatus, IntegrationStatus, JobRole, JobState
from app.domain.tasks import TaskState


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    priority: int = Field(default=3, ge=0, le=5)
    external_key: str | None = Field(default=None, max_length=100)
    enqueue_planning: bool = True
    repository_id: uuid.UUID | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    external_key: str | None
    title: str
    description: str
    priority: int
    state: TaskState
    current_revision: str | None
    repository_id: uuid.UUID | None
    branch_name: str | None
    workspace_path: str | None
    pull_request_number: int | None
    pull_request_url: str | None
    manual_takeover: bool
    created_at: datetime
    updated_at: datetime


class JobCreate(BaseModel):
    role: JobRole
    action: str = Field(min_length=1, max_length=100)
    priority: int = Field(default=3, ge=0, le=5)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID
    role: JobRole
    action: str
    priority: int
    state: JobState
    attempt: int
    payload: dict[str, Any]
    result: dict[str, Any] | None
    worker_id: str | None
    failure_reason: str | None
    retry_not_before: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: uuid.UUID
    source: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class WorkerResult(BaseModel):
    protocol_version: int = 1
    job_id: uuid.UUID
    task_id: uuid.UUID
    role: JobRole
    result: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class WorkerNodeRead(BaseModel):
    id: str
    hostname: str
    process_id: int
    status: str
    online: bool
    capabilities: list[str]
    started_at: datetime
    last_heartbeat: datetime
    stopped_at: datetime | None


class IntegrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    provider_type: str
    provider_name: str
    status: IntegrationStatus
    configuration: dict[str, Any]
    has_credentials: bool
    last_error: str | None
    updated_at: datetime


class IntegrationUpdate(BaseModel):
    provider_type: str = Field(min_length=1, max_length=50)
    status: IntegrationStatus = IntegrationStatus.CONFIGURED
    configuration: dict[str, Any] = Field(default_factory=dict)
    credential: SecretStr | None = None


class RepositoryCreate(BaseModel):
    provider: str = "github"
    external_repo_id: str = Field(min_length=1, max_length=255)
    owner: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    clone_url: str = Field(min_length=1)
    default_branch: str = "main"


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    provider: str
    external_repo_id: str
    owner: str
    name: str
    clone_url: str
    default_branch: str
    enabled: bool
    local_path: str | None
    latest_sha: str | None
    indexed_sha: str | None
    indexed_at: datetime | None
    index_status: IndexStatus
    index_error: str | None
    updated_at: datetime
    clone_status: str = "NOT_CLONED"
    chunk_count: int = 0


class AgentConfigUpdate(BaseModel):
    enabled: bool = True
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(max_length=255)
    configuration: dict[str, Any] = Field(default_factory=dict)


class AgentConfigRead(AgentConfigUpdate):
    model_config = ConfigDict(from_attributes=True)
    role: AgentRole
    updated_at: datetime
    status: str = "READY"
    active_jobs: int = 0
    total_runs: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_estimated_cost_usd: float = 0
    last_run_at: datetime | None = None
    last_duration_ms: int | None = None
    last_provider: str | None = None
    last_model: str | None = None


class AgentKnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=20, max_length=500_000)


class AgentKnowledgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: AgentRole
    title: str
    chunk_count: int
    created_at: datetime


class WorkflowNodeRead(BaseModel):
    id: uuid.UUID
    role: str
    label: str = Field(min_length=1, max_length=100)
    position_x: float
    position_y: float
    enabled: bool = True
    activation_policy: str = "any"
    batch_window_seconds: int = Field(default=0, ge=0, le=300)


class WorkflowEdgeRead(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    outcome: str = "success"
    required: bool = True


class WorkflowGraphRead(BaseModel):
    version: int = Field(ge=0)
    nodes: list[WorkflowNodeRead]
    edges: list[WorkflowEdgeRead]


class ProviderModelRead(BaseModel):
    id: str
    display_name: str


class ProviderCatalogRead(BaseModel):
    provider: str
    capabilities: dict[str, bool]
    models: list[ProviderModelRead]


class DiscoveredRepository(BaseModel):
    external_repo_id: str
    owner: str
    name: str
    full_name: str
    clone_url: str
    default_branch: str
    private: bool


class LinearWorkflowStateRead(BaseModel):
    id: str
    name: str
    type: str
    team_id: str
    team_name: str
    team_key: str


class WebhookHealthRead(BaseModel):
    provider: str
    pending: int
    failed: int
    last_delivery_at: datetime | None
    last_processed_at: datetime | None
    last_error: str | None


class DashboardActivityRead(BaseModel):
    active_job: JobRead | None
    queued_jobs: list[JobRead]


class PullRequestRead(BaseModel):
    number: int
    url: str
    state: str
    head_sha: str
    merged: bool = False
    merge_commit_sha: str | None = None


class ValidationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    provider: str
    kind: str
    name: str
    status: str
    revision: str
    details_url: str | None
    created_at: datetime


class MergeResult(BaseModel):
    merged: bool
    sha: str | None = None
    message: str


class KnowledgeSearchResult(BaseModel):
    file_path: str
    chunk_index: int
    content: str
    commit_sha: str
    score: float


class ReviewFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    reviewer_job_id: uuid.UUID
    workspace_fingerprint: str
    finding_fingerprint: str | None
    occurrence_count: int
    severity: str
    file_path: str | None
    line: int | None
    message: str
    status: str
    created_at: datetime
    last_seen_at: datetime | None
    resolved_at: datetime | None
