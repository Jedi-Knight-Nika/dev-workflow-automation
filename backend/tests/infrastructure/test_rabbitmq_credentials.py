import os
import re
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[3] / "scripts/ensure-rabbitmq-env.sh"
KEYS = {"RABBITMQ_USER", "RABBITMQ_PASSWORD", "RABBITMQ_URL"}


@pytest.fixture
def credentials_setup(tmp_path):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text(
        '#!/bin/sh\n[ "$1" = volume ] && [ "$2" = ls ] || exit 2\n'
        '[ "${BROKER_QUERY_FAIL:-}" = true ] && exit 1\n'
        'printf "%s" "${EXISTING_BROKER_VOLUME:-}"\n'
    )
    docker.chmod(0o755)
    environment = {key: value for key, value in os.environ.items() if key not in KEYS}
    environment["PATH"] = f"{binaries}:{os.defpath}"
    env_file = tmp_path / "config with spaces" / ".env"
    env_file.parent.mkdir()
    return env_file, environment


def initialize(env_file, environment):
    return subprocess.run(
        ["sh", str(SCRIPT), str(env_file)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize(
    "initial",
    [
        "",
        "RABBITMQ_USER=\nRABBITMQ_PASSWORD=\"\"\nRABBITMQ_URL=''\n",
        "RABBITMQ_USER=engineering_worker\nRABBITMQ_PASSWORD= # not set\nRABBITMQ_URL=\n",
        (
            "RABBITMQ_USER=engineering_worker\nRABBITMQ_PASSWORD=change-me-before-deployment\n"
            "RABBITMQ_URL=amqp://engineering_worker:change-me-before-deployment@rabbitmq:5672/aew\n"
        ),
        (
            "RABBITMQ_USER=engineering_worker\nRABBITMQ_PASSWORD=replace-with-a-strong-broker-password\n"
            "RABBITMQ_URL=amqp://engineering_worker:replace-with-a-strong-broker-password@rabbitmq:5672/aew\n"
        ),
    ],
)
def test_first_setup_generates_private_matching_credentials_once(credentials_setup, initial):
    env_file, environment = credentials_setup
    untouched = "APP_SECRET_KEY=keep-this-secret\nDATABASE_URL=keep-this-url\n"
    env_file.write_text(untouched + initial)
    result = initialize(env_file, environment)
    assert result.returncode == 0, result.stderr
    content = env_file.read_text()
    values = dict(line.split("=", 1) for line in content.splitlines() if line)
    password = values["RABBITMQ_PASSWORD"]
    assert re.fullmatch("[0-9a-f]{64}", password)
    assert values["RABBITMQ_USER"] == "engineering_worker"
    assert values["RABBITMQ_URL"] == f"amqp://engineering_worker:{password}@rabbitmq:5672/aew"
    assert content.startswith(untouched)
    assert content.count("RABBITMQ_PASSWORD=") == 1
    assert env_file.stat().st_mode & 0o777 == 0o600
    assert password not in result.stdout + result.stderr
    assert not list(env_file.parent.glob(".env.rabbitmq*"))
    result = initialize(env_file, {**environment, "BROKER_QUERY_FAIL": "true"})
    assert result.returncode == 0 and env_file.read_text() == content


def test_configured_credentials_are_never_replaced_or_evaluated(credentials_setup):
    env_file, environment = credentials_setup
    marker = env_file.parent / "do-not-create"
    content = (
        "export RABBITMQ_USER='custom-user'\n"
        f'RABBITMQ_PASSWORD="$(touch {marker})"\n'
        "RABBITMQ_URL='amqps://custom-user:custom-pass@private-broker/aew'\n"
    )
    env_file.write_text(content)
    result = initialize(env_file, {**environment, "EXISTING_BROKER_VOLUME": "existing"})
    assert result.returncode == 0
    assert env_file.read_text() == content and not marker.exists()
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize(
    "content",
    [
        "RABBITMQ_USER=custom-user\n",
        "RABBITMQ_PASSWORD=existing-password\n",
        "RABBITMQ_URL=amqp://existing:password@broker/aew\n",
        "RABBITMQ_USER=engineering_worker\nRABBITMQ_PASSWORD=existing-password\nRABBITMQ_URL=\n",
    ],
)
def test_partial_custom_configuration_is_not_silently_rotated(credentials_setup, content):
    env_file, environment = credentials_setup
    env_file.write_text(content)
    result = initialize(env_file, environment)
    assert result.returncode != 0 and "incomplete" in result.stderr
    assert env_file.read_text() == content
    assert "existing-password" not in result.stderr
    assert not list(env_file.parent.glob(".env.rabbitmq*"))


@pytest.mark.parametrize(
    "override", [{"EXISTING_BROKER_VOLUME": "existing"}, {"BROKER_QUERY_FAIL": "true"}]
)
def test_missing_credentials_do_not_reset_existing_or_unreachable_broker(
    credentials_setup, override
):
    env_file, environment = credentials_setup
    env_file.write_text("APP_SECRET_KEY=unchanged\n")
    result = initialize(env_file, {**environment, **override})
    assert result.returncode != 0
    assert env_file.read_text() == "APP_SECRET_KEY=unchanged\n"
    assert not list(env_file.parent.glob(".env.rabbitmq*"))


def test_environment_credentials_override_file_without_writing_it(credentials_setup):
    env_file, environment = credentials_setup
    env_file.write_text("")
    environment.update(
        RABBITMQ_USER="custom",
        RABBITMQ_PASSWORD="custom-password",
        RABBITMQ_URL="amqp://custom:custom-password@broker/aew",
    )
    assert initialize(env_file, environment).returncode == 0
    assert env_file.read_text() == ""
    del environment["RABBITMQ_URL"]
    assert initialize(env_file, environment).returncode != 0
    assert env_file.read_text() == ""


@pytest.mark.parametrize(
    "overrides",
    [
        {"RABBITMQ_PASSWORD": ""},
        {"RABBITMQ_USER": "", "RABBITMQ_PASSWORD": "", "RABBITMQ_URL": ""},
    ],
)
def test_empty_exported_credentials_cannot_shadow_generated_file(credentials_setup, overrides):
    env_file, environment = credentials_setup
    env_file.write_text("APP_SECRET_KEY=unchanged\n")
    result = initialize(env_file, {**environment, **overrides})
    assert result.returncode != 0 and "unset" in result.stderr
    assert env_file.read_text() == "APP_SECRET_KEY=unchanged\n"
    assert not list(env_file.parent.glob(".env.rabbitmq*"))


def test_generation_failure_preserves_configuration(credentials_setup):
    env_file, environment = credentials_setup
    env_file.write_text("APP_SECRET_KEY=unchanged\n")
    openssl = Path(environment["PATH"].split(os.pathsep)[0]) / "openssl"
    openssl.write_text("#!/bin/sh\nexit 1\n")
    openssl.chmod(0o755)
    result = initialize(env_file, environment)
    assert result.returncode != 0
    assert env_file.read_text() == "APP_SECRET_KEY=unchanged\n"
    assert not list(env_file.parent.glob(".env.rabbitmq*"))


def test_concurrent_setup_refuses_to_overwrite_another_initialization(credentials_setup):
    env_file, environment = credentials_setup
    env_file.write_text("")
    lock = Path(str(env_file) + ".rabbitmq-lock")
    lock.mkdir()
    result = initialize(env_file, environment)
    assert result.returncode != 0 and "already being initialized" in result.stderr
    assert env_file.read_text() == "" and lock.is_dir()
