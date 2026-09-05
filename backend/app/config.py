from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Autonomous Engineering Worker"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+asyncpg://engineering_worker:change-me@localhost:5432/engineering_worker"
    )
    database_url_sync: str = (
        "postgresql+psycopg://engineering_worker:change-me@localhost:5432/engineering_worker"
    )
    app_secret_key: str = Field(default="development-only-secret-change-me", min_length=16)
    workspace_root: Path = Path("./workspaces")
    scheduler_enabled: bool = True
    scheduler_poll_seconds: float = 1.0
    worker_timeout_seconds: int = 300
    worker_lease_seconds: int = 330
    worker_heartbeat_seconds: float = 5.0
    max_executor_jobs_per_task: int = 5
    max_thinker_jobs_per_task: int = 3
    max_same_finding_repeats: int = 2
    max_ci_repairs_per_task: int = 3
    max_external_review_repairs_per_task: int = 3
    max_job_attempts: int = 3
    job_retry_base_seconds: int = 5
    worker_transport: Literal["local", "docker"] = "local"
    docker_socket: Path = Path("/var/run/docker.sock")
    worker_container_image: str = "autonomous-engineering-worker-runtime:latest"
    worker_container_network: str = "autonomous-engineering-worker_default"
    worker_workspace_volume: str = "autonomous-engineering-worker_workspaces"
    worker_database_url: str = ""
    worker_egress_proxy: str = ""
    worker_no_proxy: str = "postgres"
    worker_container_memory_mb: int = Field(default=1536, ge=128)
    worker_container_cpus: float = Field(default=1.5, gt=0)
    github_webhook_secret: str = ""
    github_app_return_url: str = "http://localhost:3000/integrations"
    linear_webhook_secret: str = ""

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
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
