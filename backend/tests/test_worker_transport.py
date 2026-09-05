import uuid

from app.config import Settings
from app.services.worker_transport import demultiplex_docker_logs, docker_container_spec


def test_docker_worker_is_hardened_and_receives_only_job_id() -> None:
    job_id = uuid.uuid4()

    spec = docker_container_spec(Settings(), job_id)

    assert spec["Cmd"] == [".venv/bin/python", "-m", "app.worker", str(job_id)]
    assert spec["HostConfig"]["ReadonlyRootfs"] is True
    assert spec["HostConfig"]["Privileged"] is False
    assert spec["HostConfig"]["CapDrop"] == ["ALL"]
    assert spec["HostConfig"]["SecurityOpt"] == ["no-new-privileges:true"]
    assert spec["HostConfig"]["PidsLimit"] == 128
    assert all("GITHUB_WEBHOOK_SECRET" not in value for value in spec["Env"])
    assert all("DATABASE_URL_SYNC" not in value for value in spec["Env"])


def test_docker_worker_uses_dedicated_credentials_and_optional_proxy() -> None:
    spec = docker_container_spec(
        Settings(
            worker_database_url="postgresql+asyncpg://job:secret@postgres/jobs",
            worker_egress_proxy="http://egress-proxy:3128",
            worker_no_proxy="postgres,localhost",
        ),
        uuid.uuid4(),
    )

    assert "DATABASE_URL=postgresql+asyncpg://job:secret@postgres/jobs" in spec["Env"]
    assert "HTTPS_PROXY=http://egress-proxy:3128" in spec["Env"]
    assert "NO_PROXY=postgres,localhost" in spec["Env"]


def test_docker_log_frames_are_demultiplexed() -> None:
    stdout_frame = bytes([1, 0, 0, 0]) + (5).to_bytes(4, "big") + b"hello"
    stderr_frame = bytes([2, 0, 0, 0]) + (4).to_bytes(4, "big") + b"oops"

    assert demultiplex_docker_logs(stdout_frame + stderr_frame) == (b"hello", b"oops")
