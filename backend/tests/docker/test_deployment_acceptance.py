"""Backup/restore and reverse-proxy checks against the dedicated acceptance stack."""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_ACCEPTANCE") != "true", reason="Unpaid Docker acceptance is opt-in"
)
ROOT = Path(__file__).resolve().parents[3]
NETWORK = "engineering-acceptance_default"


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True, timeout=90).strip()


@pytest.fixture(autouse=True)
def require_acceptance_stack() -> None:
    # Never run these database operations against an arbitrary application stack.
    project = docker(
        "inspect",
        "engineering-acceptance-postgres-1",
        "--format",
        '{{index .Config.Labels "com.docker.compose.project"}}',
    )
    assert project == "engineering-acceptance"


def test_backup_restores_database_and_all_runtime_state():
    with tempfile.TemporaryDirectory(prefix="engineering-backup-", dir="/tmp") as temporary:
        root = Path(temporary).resolve()
        source, restored, backups = (root / name for name in ("source", "restored", "backups"))
        for directory in (source, restored, backups):
            directory.mkdir()
        for name in ("workspaces", "native", "control"):
            (source / name).mkdir()
            (source / name / "fixture").write_text(f"{name} checkpoint\n")
        common = (
            "run",
            "--rm",
            "--network",
            NETWORK,
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "PGHOST=postgres",
            "-e",
            "PGUSER=acceptance",
            "-e",
            "PGPASSWORD=acceptance-only",
            "-e",
            "CONFIRM_QUIESCENT=YES",
        )
        docker(
            *common,
            "-e",
            "PGDATABASE=acceptance",
            "-v",
            f"{source}:/engineering-data:ro",
            "-v",
            f"{backups}:/backups",
            "-v",
            f"{ROOT}/deploy/backup.sh:/backup.sh:ro",
            "postgres:16",
            "sh",
            "/backup.sh",
        )
        sets = list(backups.iterdir())
        assert len(sets) == 1 and not sets[0].name.startswith("incomplete")
        destination = f"acceptance_restore_{uuid4().hex}"
        restore_args = (
            *common,
            "-e",
            f"RESTORE_DATABASE={destination}",
            "-e",
            "CONFIRM_RESTORE=RESTORE",
            "-e",
            f"BACKUP_SET={sets[0].name}",
            "-v",
            f"{restored}:/engineering-data",
            "-v",
            f"{backups}:/backups:ro",
            "-v",
            f"{ROOT}/deploy/restore.sh:/restore.sh:ro",
            "postgres:16",
            "sh",
            "/restore.sh",
        )
        docker(*restore_args)
        for name in ("workspaces", "native", "control"):
            assert (restored / name / "fixture").read_bytes() == (
                source / name / "fixture"
            ).read_bytes()
        query = (
            "SELECT (SELECT version_num FROM alembic_version), "
            "(SELECT count(*) FROM teams), (SELECT count(*) FROM team_agent_profiles)"
        )
        rows = [
            docker(*common, "postgres:16", "psql", "-d", db, "-At", "-c", query)
            for db in ("acceptance", destination)
        ]
        assert rows[0] == rows[1] and rows[0].startswith("0001_initial|")
        # Recovery must never overwrite nonempty state on an accidental second invocation.
        with pytest.raises(subprocess.CalledProcessError):
            docker(*restore_args)


def test_caddy_protects_console_but_forwards_signed_webhook_boundary():
    password = "acceptance-only"
    hashed = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "caddy:2.10-alpine",
        "caddy",
        "hash-password",
        "--plaintext",
        password,
    )
    name = f"acceptance-proxy-{uuid4().hex}"
    try:
        docker(
            "run",
            "-d",
            "--name",
            name,
            "--network",
            NETWORK,
            "-p",
            "127.0.0.1::8080",
            "-e",
            "DOMAIN=:8080",
            "-e",
            "OPERATOR_USER=acceptance",
            "-e",
            f"OPERATOR_PASSWORD_HASH={hashed}",
            "-v",
            f"{ROOT}/deploy/Caddyfile:/etc/caddy/Caddyfile:ro",
            "caddy:2.10-alpine",
        )
        port = docker("port", name, "8080/tcp").rsplit(":", 1)[1]
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
            deadline = time.monotonic() + 15
            while True:
                try:
                    unauthenticated = client.get("/health/ready")
                    break
                except httpx.TransportError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
            assert unauthenticated.status_code == 401
            assert client.get("/").status_code == 401
            assert client.get("/health/ready", auth=("acceptance", password)).status_code == 200
            assert client.get("/", auth=("acceptance", password)).status_code == 200
            webhook = client.post("/webhooks/github", json={})
            # No console Basic challenge for providers; unsigned events still fail at the API.
            assert "www-authenticate" not in webhook.headers
            assert webhook.status_code in {400, 401, 403, 503}
    finally:
        # The random, exact name was created exclusively for this test.
        docker("rm", "-f", name)
