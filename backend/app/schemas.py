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
    project_name: str | None = Field(default=None, max_length=255)
    labels: list[str] = Field(default_factory=list, max_length=50)
    estimate: float | None = Field(default=None, ge=0, le=1000000)
    due_at: datetime | None = None


class ExternalTaskRead(BaseModel):
    provider: str
    external_id: str
    identifier: str
    url: str | None
    state_id: str | None
    state_name: str | None
    assignee_id: str | None
    assignee_name: str | None
    assignee_email: str | None
    creator_name: str | None
    team_name: str | None
    team_key: str | None
    project_name: str | None
    labels: list[str]
    estimate: float | None
    due_date: str | None
    provider_created_at: str | None
    provider_updated_at: str | None
    raw_payload: dict[str, Any]


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
    source: ExternalTaskRead | None = None
    repository_name: str | None = None
    due_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    project_name: str | None = None
    labels: list[str] = Field(default_factory=list)
    estimate: float | None = None
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
    active_task_id: uuid.UUID | None = None
    active_task_manual_takeover: bool = False
    active_task_has_workspace: bool = False


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
    model_config = ConfigDict(protected_namespaces=("model_dump",))

    id: uuid.UUID
    role: str
    label: str = Field(min_length=1, max_length=100)
    position_x: float
    position_y: float
    enabled: bool = True
    activation_policy: str = "any"
    batch_window_seconds: int = Field(default=0, ge=0, le=300)
    integration_ids: list[uuid.UUID] = Field(default_factory=list)
    repository_ids: list[uuid.UUID] = Field(default_factory=list)
    provider: str = Field(default="openai", pattern="^(openai|anthropic|google)$")
    model: str = Field(default="", max_length=255)
    system_prompt: str = Field(default="", max_length=100_000)
    model_validation_status: str = "NOT_CONFIGURED"
    model_validation_message: str | None = None
    model_validated_at: datetime | None = None
    integration_mode: str = Field(default="webhook", pattern="^(webhook|poll|hybrid|manual)$")
    poll_interval_seconds: int = Field(default=300, ge=60, le=86_400)
    filter_assignee_id: str = Field(default="", max_length=255)
    filter_state_ids: list[str] = Field(default_factory=list)
    integration_sync_status: str = "IDLE"
    integration_sync_error: str | None = None
    integration_last_synced_at: datetime | None = None
    reasoning_effort: str = Field(default="default", pattern="^(default|low|medium|high|max)$")
    max_output_tokens: int | None = Field(default=None, ge=256, le=200_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    timeout_minutes: int = Field(default=60, ge=1, le=720)
    max_retries: int = Field(default=2, ge=0, le=10)
    max_review_cycles: int = Field(default=3, ge=0, le=20)
    context_depth: str = Field(default="normal", pattern="^(low|normal|deep)$")
    rag_retrieval_depth: str = Field(default="normal", pattern="^(low|normal|deep)$")
    fallback_provider: str | None = Field(default=None, pattern="^(openai|anthropic|google)$")
    fallback_model: str | None = Field(default=None, max_length=255)
    agent_id: uuid.UUID | None = None


class LinearMemberRead(BaseModel):
    id: str
    name: str
    email: str
    active: bool


class WorkflowNodeModelValidationRead(BaseModel):
    node_id: uuid.UUID
    status: str
    message: str | None = None
    validated_at: datetime


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


class TerminalOpen(BaseModel):
    node_id: uuid.UUID | None = None
    cols: int = Field(default=120, ge=40, le=300)
    rows: int = Field(default=32, ge=10, le=100)


class TerminalAccessRead(BaseModel):
    session_id: uuid.UUID
    token: str
    status: str
    cols: int
    rows: int


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


class TeamWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    enabled: bool = True
    max_concurrent_tasks: int = Field(default=1, ge=1, le=32)
    repository_ids: list[uuid.UUID] = Field(default_factory=list)


class RoleWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str
    description: str = Field(default="", max_length=4000)
    system_instructions: str = Field(default="", max_length=100_000)
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    allowed_results: list[str] = Field(default_factory=list)
    knowledge_collection_ids: list[uuid.UUID] = Field(default_factory=list)
    default_provider: str | None = None
    default_model: str | None = Field(default=None, max_length=255)
    default_reasoning_effort: str = "default"
    default_timeout_minutes: int = Field(default=30, ge=1, le=720)
    default_max_retries: int = Field(default=2, ge=0, le=10)
    enabled: bool = True


class RoleRead(RoleWrite):
    id: uuid.UUID
    built_in: bool
    version: int
    active_agents: int
    created_at: datetime
    updated_at: datetime


class RoleClone(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TeamRead(TeamWrite):
    id: uuid.UUID
    queued_tasks: int
    running_tasks: int
    completed_tasks: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    created_at: datetime
    updated_at: datetime


class TaskAssignmentCreate(BaseModel):
    task_id: uuid.UUID
    reason: str = Field(default="manual", max_length=500)


class TaskAssignmentRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    team_id: uuid.UUID
    status: str
    queue_position: int
    reason: str
    assigned_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
