import pytest
from pydantic import ValidationError

from app.config import Settings


def production_settings(**overrides: str) -> Settings:
    values = {
        "environment": "production",
        "app_secret_key": "app-secret-00000000000000000000000000000000",
        "github_webhook_secret": "github-secret-00000000000000000000000000000",
        "linear_webhook_secret": "linear-secret-000000000000000000000000000000",
        "database_url": "postgresql+asyncpg://worker:strong@postgres:5432/worker",
        "database_url_sync": "postgresql+psycopg://worker:strong@postgres:5432/worker",
        "github_app_return_url": "https://worker.example.com/integrations",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_production_accepts_distinct_non_placeholder_secrets() -> None:
    settings = production_settings()

    assert settings.environment == "production"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("app_secret_key", "development-only-secret-change-me"),
        ("github_webhook_secret", ""),
        ("linear_webhook_secret", "replace-with-a-random-webhook-secret"),
    ],
)
def test_production_rejects_missing_weak_or_placeholder_secrets(name: str, value: str) -> None:
    with pytest.raises(ValidationError, match=name.upper()):
        production_settings(**{name: value})


def test_production_rejects_reused_secrets() -> None:
    shared = "shared-secret-000000000000000000000000000000"

    with pytest.raises(ValidationError, match="must be unique"):
        production_settings(app_secret_key=shared, github_webhook_secret=shared)


@pytest.mark.parametrize("name", ["database_url", "database_url_sync"])
def test_production_rejects_placeholder_database_urls(name: str) -> None:
    with pytest.raises(ValidationError, match=name.upper()):
        production_settings(**{name: "postgresql://worker:change-me@postgres/worker"})


@pytest.mark.parametrize(
    "return_url", ["http://worker.example.com/integrations", "localhost:3000/integrations"]
)
def test_production_requires_absolute_https_github_return_url(return_url: str) -> None:
    with pytest.raises(ValidationError, match="absolute HTTPS"):
        production_settings(github_app_return_url=return_url)


def test_development_keeps_local_zero_configuration_defaults() -> None:
    settings = Settings(environment="development")

    assert settings.github_webhook_secret == ""
