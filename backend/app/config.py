from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Autonomous Engineering Worker"
    environment: str = "development"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
