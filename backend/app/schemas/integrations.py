from __future__ import annotations

# Schema modules share a small validation vocabulary.
# ruff: noqa: F401
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.domain.agents import AgentRole
from app.domain.operational_states import IndexStatus, IntegrationStatus, JobRole, JobState
from app.domain.tasks import TaskState


class TelegramConfigure(BaseModel):
    bot_token: SecretStr
    webhook_base_url: str | None = Field(default=None, max_length=2000)


class IntegrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    provider_type: str
    provider_name: str
    status: IntegrationStatus
    configuration: dict[str, Any]
    has_credentials: bool
    last_error: str | None
    sync_status: str
    last_synced_at: datetime | None
    updated_at: datetime
    display_status: str = "NOT_CONFIGURED"
    usage: dict[str, int] = Field(default_factory=dict)


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


class RepositoryBatchImport(BaseModel):
    repositories: list[RepositoryCreate] = Field(min_length=1, max_length=100)
    prepare_knowledge: bool = True


class RepositoryDependenciesRead(BaseModel):
    teams: tuple[str, ...] = ()
    active_tasks: int = 0
    active_workspaces: int = 0
    task_sources: tuple[str, ...] = ()


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
    archived_at: datetime | None = None
    code_status: str = "NOT_PREPARED"
    knowledge_status: str = "NOT_PREPARED"
    teams_count: int = 0
    active_tasks_count: int = 0
    active_workspaces_count: int = 0
    last_activity_at: datetime | None = None


class LinearMemberRead(BaseModel):
    id: str
    name: str
    email: str
    active: bool


class TrelloBoardRead(BaseModel):
    id: str
    name: str
    url: str


class TrelloListRead(BaseModel):
    id: str
    name: str
    closed: bool


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


class PullRequestRead(BaseModel):
    number: int
    url: str
    state: str
    head_sha: str
    merged: bool = False
    merge_commit_sha: str | None = None


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
