"""Real Docker checks with no inference, credentials or application database.

Opt in on the Docker host with RUN_DOCKER_ACCEPTANCE=true. Build the acceptance
developer image first. Every checkout/state directory is a fresh temporary path;
the production container specifications and cleanup implementation run unchanged.
"""

import asyncio
import json
import os
import subprocess
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from app.agent_runtime.infrastructure.container import (
    RunnerMounts,
    developer_container_spec,
    validation_container_spec,
)
from app.agent_runtime.infrastructure.container_job import run_container_job

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_ACCEPTANCE") != "true", reason="Unpaid Docker acceptance is opt-in"
)
IMAGE = "engineering-acceptance-developer:local"


@pytest_asyncio.fixture
async def docker() -> AsyncIterator[httpx.AsyncClient]:
    endpoint = os.getenv("DOCKER_HOST", "")
    socket = endpoint.removeprefix("unix://") if endpoint else "/var/run/docker.sock"
    if not endpoint and not Path(socket).exists():
        socket = str(Path.home() / ".docker/run/docker.sock")
    if endpoint and not endpoint.startswith("unix://"):
        pytest.fail("Acceptance requires an explicit local Unix Docker socket")
    async with httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(uds=socket), base_url="http://docker", timeout=30
    ) as client:
        (await client.get(f"/images/{IMAGE}/json")).raise_for_status()
        yield client


def git(workspace: Path, *args: str) -> str:
    return subprocess.check_output(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.name=Acceptance",
            "-c",
            "user.email=acceptance@localhost",
            "-c",
            f"safe.directory={workspace}",
            *args,
        ],
        cwd=workspace,
        text=True,
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
    ).strip()


@pytest.fixture
def mounts() -> Iterator[RunnerMounts]:
    with tempfile.TemporaryDirectory(prefix="engineering-docker-", dir="/tmp") as temporary:
        root, task_id = Path(temporary).resolve(), uuid4()
        workspace = root / "workspaces" / str(task_id) / "repo"
        state = root / "native" / str(task_id)
        control = root / "control" / str(task_id)
        for directory in (workspace, state, control):
            directory.mkdir(parents=True)
        # Docker Desktop maps host ownership; Linux CI needs access by runner UID.
        # These are newly created, non-sensitive acceptance fixtures only.
        for directory in (root, *root.rglob("*")):
            if directory.is_dir():
                directory.chmod(0o777)
        git(workspace, "init", "-b", "agent/acceptance")
        (workspace / "sample.txt").write_text("before\n")
        git(workspace, "add", ".")
        git(workspace, "commit", "-m", "fixture")
        base = git(workspace, "rev-parse", "HEAD")
        (workspace / "sample.txt").write_text("after\n")
        (state / "private-marker").write_text("never mount in validation")
        manifest = control / "task.json"
        manifest.write_text(
            json.dumps(
                {
                    "branch": "agent/acceptance",
                    "title": "Acceptance change",
                    "author_name": "Acceptance Team",
                    "base_sha": base,
                    "commands": [["/app/.venv/bin/python", "-c", "assert 2 + 2 == 4"]],
                    "timeout_seconds": 10,
                }
            )
        )
        (control / "workspace.lock").touch(mode=0o644)
        # Git objects are also shared with the non-root test runner.
        for path in workspace.rglob("*"):
            path.chmod(0o777 if path.is_dir() else 0o666)
        # In production the Git-only runner creates the checkout as UID 10001.
        # Match that ownership here instead of disabling Git's ownership protection.
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0:0",
                "-v",
                f"{workspace}:/fixture",
                IMAGE,
                "chown",
                "-R",
                "10001:10001",
                "/fixture",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        yield RunnerMounts(
            task_id,
            workspace,
            state,
            manifest,
            root / "workspaces",
            root / "native",
            root / "control",
        )


def command(mounts: RunnerMounts, script: str) -> None:
    manifest = json.loads(mounts.manifest.read_text())
    manifest["commands"] = [["/app/.venv/bin/python", "-c", script]]
    mounts.manifest.write_text(json.dumps(manifest))


async def test_validation_commits_with_real_isolation(docker, mounts):
    config_before = (mounts.workspace / ".git/config").read_bytes()
    command(
        mounts,
        """
import os, socket
from pathlib import Path
assert os.getuid() == 10001
assert not Path('/home/runner/private-marker').exists()
assert not Path('/var/run/docker.sock').exists()
assert all(not os.getenv(k) for k in ('DATABASE_URL', 'OPENAI_API_KEY', 'GITHUB_TOKEN'))
# Docker Desktop may expose dormant tunnel devices even with network=none.
assert len(Path('/proc/net/route').read_text().splitlines()) == 1
try:
    socket.create_connection(('192.0.2.1', 443), timeout=0.2)
except OSError:
    pass
else:
    raise AssertionError('Validator unexpectedly has an external route')
assert not os.access('/app', os.W_OK)
assert not os.access('/run/control/task.json', os.W_OK)
assert Path('sample.txt').read_text() == 'after\\n'
""",
    )
    name = f"acceptance-validation-{uuid4().hex}"
    receipt = await run_container_job(
        docker, name, validation_container_spec(mounts, image=IMAGE), 40
    )
    assert receipt["passed"] is True, receipt["checks"]
    assert "sample.txt" in receipt["change_context"]
    assert receipt["checks"][0]["started_at"] <= receipt["checks"][0]["finished_at"]
    assert git(mounts.workspace, "status", "--porcelain") == ""
    assert git(mounts.workspace, "show", "-s", "--format=%an|%cn") == (
        "Acceptance Team|Acceptance Team"
    )
    assert (mounts.workspace / ".git/config").read_bytes() == config_before
    assert (await docker.get(f"/containers/{name}/json")).status_code == 404


async def test_failed_validation_keeps_changes_without_commit(docker, mounts):
    base = git(mounts.workspace, "rev-parse", "HEAD")
    command(mounts, "raise SystemExit(7)")
    result = await run_container_job(
        docker,
        f"acceptance-failed-{uuid4().hex}",
        validation_container_spec(mounts, image=IMAGE),
        30,
    )
    assert result["passed"] is False
    assert result["checks"][0]["exit_code"] == 7
    assert git(mounts.workspace, "rev-parse", "HEAD") == base
    assert (mounts.workspace / "sample.txt").read_text() == "after\n"


async def test_test_generated_changes_cannot_be_published(docker, mounts):
    base = git(mounts.workspace, "rev-parse", "HEAD")
    command(mounts, "from pathlib import Path; Path('sample.txt').write_text('unvalidated')")
    with pytest.raises(RuntimeError, match="Isolated operation failed"):
        await run_container_job(
            docker,
            f"acceptance-mutating-{uuid4().hex}",
            validation_container_spec(mounts, image=IMAGE),
            30,
        )
    assert git(mounts.workspace, "rev-parse", "HEAD") == base


@pytest.mark.parametrize("cancel", [False, True], ids=["timeout", "cancel"])
async def test_interruption_removes_only_its_runner(docker, mounts, cancel):
    spec = validation_container_spec(mounts, image=IMAGE)
    spec["Cmd"] = ["/app/.venv/bin/python", "-c", "import time; time.sleep(120)"]
    name = f"acceptance-interrupt-{uuid4().hex}"
    task = asyncio.create_task(run_container_job(docker, name, spec, 2 if not cancel else 60))
    if cancel:
        async with asyncio.timeout(20):
            while True:
                response = await docker.get(f"/containers/{name}/json")
                if response.status_code == 200 and response.json()["State"]["Running"]:
                    break
                await asyncio.sleep(0.1)
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
        await task
    assert (await docker.get(f"/containers/{name}/json")).status_code == 404
    assert (mounts.workspace / "sample.txt").exists()


async def test_helper_has_read_only_source_and_its_own_home(docker, mounts):
    spec = developer_container_spec(
        mounts, image=IMAGE, network="acceptance-unused", provider_environment={}, read_only=True
    )
    spec["HostConfig"]["NetworkMode"] = "none"
    spec["Cmd"] = [
        "/app/.venv/bin/python",
        "-c",
        """
import json, os
from pathlib import Path
assert os.getuid() == 10001
assert Path('sample.txt').read_text() == 'after\\n'
try:
    Path('sample.txt').write_text('forbidden')
except OSError:
    pass
else:
    raise AssertionError('Read-only helper wrote source')
Path('/home/runner/helper-state').write_text('checkpoint')
print(json.dumps({'passed': True}))
""",
    ]
    result = await run_container_job(docker, f"acceptance-helper-{uuid4().hex}", spec, 30)
    assert result["passed"] is True
    assert (mounts.state / "helper-state").read_text() == "checkpoint"


async def test_native_binaries_start_without_inference(docker, mounts):
    # Start/inspect/close is a local app-server operation. No turn is submitted,
    # only a fake key is supplied and the container has no network interface.
    spec = developer_container_spec(
        mounts, image=IMAGE, network="acceptance-unused", provider_environment={}
    )
    spec["HostConfig"]["NetworkMode"] = "none"
    spec["Env"] = ["HOME=/home/runner", "OPENAI_API_KEY=acceptance-fake-key"]
    spec["Cmd"] = [
        "/app/.venv/bin/python",
        "-c",
        """
import asyncio, json, subprocess
from pathlib import Path
import claude_agent_sdk
from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.infrastructure.codex import CodexHarness
from app.agent_runtime.infrastructure.preflight import check_workspace
async def check():
    await check_workspace(Path('/workspace'))
    harness = CodexHarness(HarnessSettings(
        model='acceptance-no-inference', workspace=Path('/workspace'), instructions='No turns.'
    ))
    try:
        session = await harness.start()
        assert session
        assert (await harness.inspect())['native_session_id'] == session
        assert not Path('/home/runner/.codex/auth.json').exists()
    finally:
        await harness.close()
    # An empty thread has no rollout to resume until its first actual turn.
    binary = Path(claude_agent_sdk.__file__).parent / '_bundled/claude'
    version = subprocess.check_output([str(binary), '--version'], text=True, timeout=15).strip()
    print(json.dumps({'codex_session_created': True, 'claude_version': version}))
try:
    asyncio.run(check())
except Exception as exc:
    # Fake-key, network-disabled fixture only: expose its setup error to pytest.
    print(json.dumps({'fixture_error': str(exc)[:1500]}))
""",
    ]
    receipt = await run_container_job(docker, f"acceptance-native-{uuid4().hex}", spec, 60)
    assert "fixture_error" not in receipt, receipt
    assert receipt["codex_session_created"] is True
    assert receipt["claude_version"]


async def test_unusable_git_metadata_is_rejected_before_native_login(docker, mounts):
    spec = developer_container_spec(
        mounts, image=IMAGE, network="acceptance-unused", provider_environment={}
    )
    spec["HostConfig"]["NetworkMode"] = "none"
    spec["Cmd"] = [
        "/app/.venv/bin/python",
        "-c",
        """
import asyncio, json
from pathlib import Path
from app.agent_runtime.application.harness import WorkspaceUnavailable
from app.agent_runtime.infrastructure.preflight import check_workspace
async def check():
    metadata = Path('/workspace/.git')
    mode = metadata.stat().st_mode & 0o777
    try:
        metadata.chmod(0)
        try:
            await check_workspace(Path('/workspace'))
        except WorkspaceUnavailable:
            print(json.dumps({'rejected_before_login': True}))
        else:
            raise AssertionError('Unusable checkout was accepted')
    finally:
        metadata.chmod(mode)
asyncio.run(check())
""",
    ]
    receipt = await run_container_job(docker, f"acceptance-preflight-{uuid4().hex}", spec, 30)
    assert receipt["rejected_before_login"] is True
