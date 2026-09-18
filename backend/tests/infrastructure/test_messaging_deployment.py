import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]


def test_messaging_is_a_normal_backend_dependency():
    project = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())["project"]
    assert any(dependency.startswith("aio-pika") for dependency in project["dependencies"])
    assert "messaging" not in project["optional-dependencies"]
    assert not (ROOT / "deploy/compose.messaging.yaml").exists()


@pytest.mark.parametrize(
    "base,overlays",
    [
        ("compose.yaml", []),
        ("compose.yaml", ["deploy/compose.execution.yaml"]),
        ("compose.yaml", ["deploy/compose.execution.yaml", "deploy/compose.observability.yaml"]),
        ("deploy/compose.production.yaml", []),
        ("deploy/compose.production.yaml", ["deploy/compose.execution.yaml"]),
    ],
)
def test_every_standard_stack_includes_private_persistent_messaging(base, overlays):
    if not shutil.which("docker"):
        pytest.skip("Docker CLI is required to validate Compose configuration")
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "DOMAIN": "example.test",
        "OPERATOR_USER": "test",
        "OPERATOR_PASSWORD_HASH": "test-hash",
        "POSTGRES_PASSWORD": "test-only",
        "DATABASE_URL": "postgresql+asyncpg://test:test@postgres/test",
        "DATABASE_URL_SYNC": "postgresql+psycopg://test:test@postgres/test",
        "APP_SECRET_KEY": "test-only",
        "GITHUB_WEBHOOK_SECRET": "test-only",
        "LINEAR_WEBHOOK_SECRET": "test-only",
        "GITHUB_APP_RETURN_URL": "https://example.test/integrations",
        "RABBITMQ_USER": "test",
        "RABBITMQ_PASSWORD": "test-only",
        "RABBITMQ_URL": "amqp://test:test-only@rabbitmq:5672/aew",
        "EXECUTION_DATA_ROOT": "/tmp/test-execution",
        "OLLAMA_IMAGE": "ollama/ollama:test",
        "OBSERVABILITY_CONFIG_ROOT": str(ROOT / "monitoring"),
        "METRICS_TOKEN_FILE": "/tmp/test-metrics-token",
        "OBSERVABILITY_ALERT_TOKEN_FILE": "/tmp/test-alert-token",
        "POSTGRES_MONITOR_PASSWORD_FILE": "/tmp/test-monitor-password",
    }
    command = ["docker", "compose", "--env-file", os.devnull]
    for path in (base, *overlays):
        command.extend(["-f", str(ROOT / path)])
    result = subprocess.run(
        [*command, "config", "--format", "json"],
        env=environment,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    configuration = json.loads(result.stdout)
    services = configuration["services"]
    assert (
        services["backend"]["depends_on"]["migrate"]["condition"]
        == "service_completed_successfully"
    )
    assert services["migrate"]["command"] == [".venv/bin/alembic", "upgrade", "head"]
    assert services["migrate"]["restart"] == "no"
    broker, messaging = services["rabbitmq"], services["messaging"]
    assert not broker.get("profiles") and not messaging.get("profiles")
    assert not broker.get("ports") and not messaging.get("ports")
    assert broker["restart"] == messaging["restart"] == "unless-stopped"
    assert broker["volumes"][0]["source"] == "rabbitmq_data"
    assert "rabbitmq_data" in configuration["volumes"]
    assert messaging["depends_on"]["backend"]["condition"] == "service_healthy"
    assert messaging["depends_on"]["rabbitmq"]["condition"] == "service_healthy"
    assert messaging["command"] == [".venv/bin/python", "-m", "app.messaging_runner"]
    assert messaging["build"]["target"] == "api"
    assert messaging["environment"]["RABBITMQ_URL"] == environment["RABBITMQ_URL"]
    for name in ("backend", "worker", "activity", "messaging"):
        assert "EVENT_TRANSPORT" not in services[name].get("environment", {})
    for name in ("backend", "worker", "activity"):
        assert "RABBITMQ_URL" not in services[name].get("environment", {})
