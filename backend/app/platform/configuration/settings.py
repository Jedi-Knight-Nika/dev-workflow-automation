from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Compose leaves optional settings blank. Ignore those values so typed
    # defaults apply; populated JSON must still parse and validate strictly.
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")
    app_name: str = "Autonomous Engineering Worker"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+asyncpg://engineering_worker:change-me@localhost:5432/engineering_worker"
    )
    database_url_sync: str = (
        "postgresql+psycopg://engineering_worker:change-me@localhost:5432/engineering_worker"
    )
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    database_pool_recycle_seconds: int = Field(default=1800, ge=60, le=86_400)
    database_pool_timeout_seconds: int = Field(default=30, ge=1, le=300)
    app_secret_key: str = Field(default="development-only-secret-change-me", min_length=16)
    workspace_root: Path = Path("./workspaces")
    scheduler_enabled: bool = False
    scheduler_poll_seconds: float = 1.0
    scheduler_max_concurrent_jobs: int = Field(default=2, ge=1, le=32)
    docker_api_timeout_seconds: int = Field(default=30, ge=1, le=300)
    worker_lease_seconds: int = 330
    worker_heartbeat_seconds: float = 5.0
    docker_socket: Path = Path("/var/run/docker.sock")
    github_webhook_secret: str = ""
    github_app_slug: str = ""
    github_app_id: str = ""
    github_app_private_key: str = ""
    github_app_private_key_file: Path | None = None
    github_app_return_url: str = "http://localhost:3000/repositories"
    linear_webhook_secret: str = ""
    # Fresh installations use the fixed lifecycle. Enabling paid execution remains an explicit step.
    developer_harness_codex: bool = False
    developer_harness_claude: bool = False
    local_event_interpreter: bool = False
    harness_state_root: Path = Path("./harness-state")
    harness_control_root: Path = Path("./harness-control")
    developer_container_image: str = "engineering-developer:local"
    developer_container_network: str = "engineering-provider-internal"
    developer_egress_proxy: str = ""
    developer_turn_timeout_seconds: int = Field(default=1200, ge=1, le=7200)
    # Zero keeps native automatic compaction only. Opt in after the SDK smoke test.
    developer_compact_before_feedback_tokens: int = Field(default=0, ge=0, le=10000000)
    repository_validation_commands: dict[str, list[list[str]]] = Field(default_factory=dict)
    ollama_base_url: str = "http://ollama:11434"
    observer_enabled: bool = True
    observer_local_ai_enabled: bool = False
    observer_model: str = Field(default="qwen3.5:4b", max_length=100)
    # Includes model load/KV cache headroom plus the operator's engineering reserve.
    # Zero fails closed; it never means unlimited admission.
    observer_min_available_memory_mb: int = Field(default=0, ge=0, le=1048576)
    observer_proactive_cooldown_seconds: int = Field(default=900, ge=60, le=86400)
    interpreter_model: str = "qwen3:4b"
    interpreter_timeout_seconds: int = Field(default=30, ge=1, le=120)
    interpreter_cloud_models: list[str] = Field(default_factory=list, max_length=2)
    interpreter_cloud_request_limit_usd: float = Field(
        default=0.02, gt=0, le=0.1, allow_inf_nan=False
    )
    slack_signing_secret: str = ""
    slack_team_routes: dict[str, dict[str, str]] = Field(default_factory=dict)
    github_issue_routes: dict[str, dict[str, str]] = Field(default_factory=dict)
    trello_webhook_secret: str = ""
    trello_webhook_callback_url: str = ""
    # Supporting planes are opt-in and never participate in execution admission.
    observability_enabled: bool = False
    prometheus_url: str = "http://prometheus:9090"
    observability_host_id: str = Field(default="local", pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    observability_compose_project: str = "autonomous-engineering-worker"
    observability_timeout_seconds: float = Field(default=3, ge=0.2, le=10)
    observability_live_refresh_seconds: int = Field(default=5, ge=5, le=60)
    observability_retention_days: int = Field(default=30, ge=1, le=90)
    observability_retention_size: str = Field(default="5GB", pattern=r"^[1-9][0-9]*(MB|GB|TB)$")
    observability_cpu_warning: int = Field(default=90, ge=1, le=100)
    observability_ram_warning: int = Field(default=85, ge=1, le=100)
    observability_disk_warning: int = Field(default=85, ge=1, le=100)
    observability_queue_warning_seconds: int = Field(default=900, ge=30, le=86400)
    observability_alert_token: str = ""
    metrics_token: str = ""
    metrics_token_file: Path | None = None
    observability_alert_token_file: Path | None = None
    forecasts_enabled: bool = False
    forecast_min_samples: int = Field(default=5, ge=3, le=100)
    forecast_horizon_days: int = Field(default=7, ge=1, le=30)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        for target in ("metrics_token", "observability_alert_token"):
            file = getattr(self, target + "_file")
            if file is not None:
                value = file.read_text().strip()
                if len(value) < 32 or len(value) > 256:
                    raise ValueError("Monitoring secret files require 32–256 characters")
                setattr(self, target, value)
        if self.environment.lower() != "production":
            return self
        secrets = {
            "APP_SECRET_KEY": self.app_secret_key,
            "GITHUB_WEBHOOK_SECRET": self.github_webhook_secret,
            "LINEAR_WEBHOOK_SECRET": self.linear_webhook_secret,
        }
        invalid_markers = ("change-me", "development-only", "replace-with")
        invalid = [
            name
            for name, value in secrets.items()
            if len(value) < 32 or any(marker in value.lower() for marker in invalid_markers)
        ]
        if invalid:
            raise ValueError(
                "Production requires non-placeholder secrets of at least 32 characters: "
                + ", ".join(invalid)
            )
        if len(set(secrets.values())) != len(secrets):
            raise ValueError("Production encryption and webhook secrets must be unique")
        database_urls = {
            "DATABASE_URL": self.database_url,
            "DATABASE_URL_SYNC": self.database_url_sync,
        }
        invalid_urls = [
            name
            for name, value in database_urls.items()
            if not value or any(marker in value.lower() for marker in invalid_markers)
        ]
        if invalid_urls:
            raise ValueError(
                "Production database URLs cannot be blank or contain placeholders: "
                + ", ".join(invalid_urls)
            )
        return_url = urlparse(self.github_app_return_url)
        if return_url.scheme != "https" or not return_url.netloc:
            raise ValueError("GITHUB_APP_RETURN_URL must be an absolute HTTPS URL in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
