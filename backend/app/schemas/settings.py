from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GeneralSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=120)
    timezone: str = "UTC"
    date_format: Literal["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY"] = "YYYY-MM-DD"
    time_format: Literal["12H", "24H"] = "24H"
    default_landing_page: Literal["dashboard", "tasks", "teams"] = "dashboard"
    default_task_view: Literal["board", "list"] = "board"
    appearance: Literal["system", "light", "dark"] = "system"
    compact_dashboard: bool = False

    @model_validator(mode="after")
    def validate_timezone(self) -> "GeneralSettings":
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return self


class AIDefaultSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_provider_id: str | None = Field(default=None, max_length=50)
    default_model: str | None = Field(default=None, max_length=255)
    default_reasoning_level: Literal["default", "low", "medium", "high", "max"] = "medium"
    default_max_output_tokens: int | None = Field(default=None, ge=256, le=200_000)
    provider_failure_behavior: Literal["PAUSE_AND_NOTIFY", "USE_CONFIGURED_FALLBACK"] = (
        "PAUSE_AND_NOTIFY"
    )
    structured_output_retry_limit: int = Field(default=2, ge=0, le=10)


class ExecutionDefaultSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_execution_mode: Literal["CONSERVATIVE", "AUTONOMOUS", "CUSTOM"] = "AUTONOMOUS"
    default_worker_runtime: Literal["LOCAL_PROCESS", "DOCKER", "WSL2"] = "LOCAL_PROCESS"
    max_concurrent_workers: int = Field(default=1, ge=1, le=32)
    default_job_timeout_seconds: int = Field(default=3600, ge=60, le=86_400)


class SafetyDefaultSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_merge_policy: Literal["ALLOW", "DENY", "REQUIRE_HUMAN"] = "REQUIRE_HUMAN"
    default_unknown_network_policy: Literal["ALLOW", "DENY", "REQUIRE_HUMAN"] = "REQUIRE_HUMAN"
    default_dependency_install_policy: Literal["ALLOW", "DENY", "REQUIRE_HUMAN"] = "ALLOW"
    default_push_task_branch_policy: Literal["ALLOW", "DENY", "REQUIRE_HUMAN"] = "ALLOW"


class KnowledgeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_index_repositories: bool = True
    incremental_index_after_merge: bool = True
    index_source_code: bool = True
    index_tests: bool = True
    index_documentation: bool = True
    ignore_generated_files: bool = True
    context_strategy: Literal["MINIMAL", "BALANCED", "DEEP"] = "BALANCED"


class StorageSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completed_workspace_retention_days: int = Field(default=7, ge=1, le=3650)
    failed_workspace_retention_days: int = Field(default=30, ge=1, le=3650)
    worker_log_retention_days: int = Field(default=30, ge=1, le=3650)
    audit_event_retention_days: int = Field(default=90, ge=30, le=3650)
    monthly_cost_warning: float | None = Field(default=None, ge=0)
    monthly_cost_hard_stop: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_cost_limits(self) -> "StorageSettings":
        if (
            self.monthly_cost_warning is not None
            and self.monthly_cost_hard_stop is not None
            and self.monthly_cost_hard_stop < self.monthly_cost_warning
        ):
            raise ValueError("monthly hard stop must be greater than or equal to warning")
        return self


SETTINGS_SECTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "general": GeneralSettings,
    "ai": AIDefaultSettings,
    "execution": ExecutionDefaultSettings,
    "safety": SafetyDefaultSettings,
    "knowledge": KnowledgeSettings,
    "storage": StorageSettings,
}
