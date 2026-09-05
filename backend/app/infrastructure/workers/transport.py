import asyncio
import os
import signal
import sys
import uuid
from typing import Any

import httpx
import psutil

from app.application.ports.worker_runtime import WorkerExecution
from app.config import Settings


def docker_container_spec(settings: Settings, job_id: uuid.UUID) -> dict[str, Any]:
    environment = [
        f"DATABASE_URL={settings.worker_database_url or settings.database_url}",
        f"APP_SECRET_KEY={settings.app_secret_key}",
        f"WORKSPACE_ROOT={settings.workspace_root}",
        "SCHEDULER_ENABLED=false",
    ]
    if settings.worker_egress_proxy:
        environment.extend(
            [
                f"HTTP_PROXY={settings.worker_egress_proxy}",
                f"HTTPS_PROXY={settings.worker_egress_proxy}",
                f"NO_PROXY={settings.worker_no_proxy}",
            ]
        )
    return {
        "Image": settings.worker_container_image,
        "Cmd": [".venv/bin/python", "-m", "app.worker", str(job_id)],
        "Env": environment,
        "AttachStdout": True,
        "AttachStderr": True,
        "Labels": {
            "app": "autonomous-engineering-worker",
            "job_id": str(job_id),
            "managed_by": "scheduler",
        },
        "HostConfig": {
            "AutoRemove": False,
            "Binds": [f"{settings.worker_workspace_volume}:/data/workspaces"],
            "NetworkMode": settings.worker_container_network,
            "ReadonlyRootfs": True,
            "Privileged": False,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m"},
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "PidsLimit": 128,
            "Memory": settings.worker_container_memory_mb * 1024 * 1024,
            "NanoCpus": int(settings.worker_container_cpus * 1_000_000_000),
            "Ulimits": [{"Name": "nofile", "Soft": 1024, "Hard": 2048}],
        },
    }


def demultiplex_docker_logs(content: bytes) -> tuple[bytes, bytes]:
    stdout = bytearray()
    stderr = bytearray()
    offset = 0
    while offset + 8 <= len(content):
        stream = content[offset]
        length = int.from_bytes(content[offset + 4 : offset + 8], "big")
        start = offset + 8
        end = start + length
        if end > len(content):
            return content, b""
        (stderr if stream == 2 else stdout).extend(content[start:end])
        offset = end
    if offset != len(content):
        return content, b""
    return bytes(stdout), bytes(stderr)


async def _run_local(settings: Settings, job_id: uuid.UUID) -> WorkerExecution:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.worker",
        str(job_id),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=settings.worker_timeout_seconds
        )
    except TimeoutError:
        await _terminate_process_tree(process.pid)
        return WorkerExecution(-1, b"", b"Worker timed out", timed_out=True)
    limit = 1_000_000
    return WorkerExecution(process.returncode or 0, stdout[-limit:], stderr[-limit:])


async def _terminate_process_tree(pid: int) -> None:
    if os.name != "nt":
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return
    try:
        parent = psutil.Process(pid)
        processes = parent.children(recursive=True) + [parent]
        for process in processes:
            process.kill()
        await asyncio.to_thread(psutil.wait_procs, processes, 3)
    except psutil.Error:
        return


async def _run_docker(settings: Settings, job_id: uuid.UUID) -> WorkerExecution:
    transport = httpx.AsyncHTTPTransport(uds=str(settings.docker_socket))
    container_id: str | None = None
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://docker",
        timeout=httpx.Timeout(settings.docker_api_timeout_seconds),
    ) as client:
        response = await client.post(
            "/containers/create",
            params={"name": f"engineering-job-{job_id}-{uuid.uuid4().hex[:8]}"},
            json=docker_container_spec(settings, job_id),
        )
        response.raise_for_status()
        container_id = response.json()["Id"]
        try:
            start = await client.post(f"/containers/{container_id}/start")
            start.raise_for_status()
            try:
                wait = await asyncio.wait_for(
                    client.post(f"/containers/{container_id}/wait", timeout=None),
                    timeout=settings.worker_timeout_seconds,
                )
            except TimeoutError:
                await client.post(f"/containers/{container_id}/kill")
                return WorkerExecution(-1, b"", b"Worker timed out", timed_out=True)
            wait.raise_for_status()
            logs = await client.get(
                f"/containers/{container_id}/logs",
                params={"stdout": True, "stderr": True},
            )
            logs.raise_for_status()
            stdout, stderr = demultiplex_docker_logs(logs.content)
            limit = 1_000_000
            return WorkerExecution(int(wait.json()["StatusCode"]), stdout[-limit:], stderr[-limit:])
        finally:
            if container_id:
                try:
                    await client.delete(f"/containers/{container_id}", params={"force": True})
                except httpx.HTTPError:
                    # Cleanup is best-effort; the scheduler must recover even when Docker is degraded.
                    pass


async def run_worker(settings: Settings, job_id: uuid.UUID) -> WorkerExecution:
    if settings.worker_transport == "docker":
        return await _run_docker(settings, job_id)
    return await _run_local(settings, job_id)
