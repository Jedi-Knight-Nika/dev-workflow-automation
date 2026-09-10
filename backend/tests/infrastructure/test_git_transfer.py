import sys
from pathlib import Path
from uuid import uuid4

import pytest

from app.agent_runtime.infrastructure.process import capture
from app.delivery.infrastructure import git_runner


@pytest.mark.asyncio
async def test_publisher_validates_real_objects_without_copying_config_or_running_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = git_runner.git
    await original(tmp_path, "init", "--initial-branch", "main", ".")
    await original(
        tmp_path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "Fixture commit",
    )
    sha = await original(tmp_path, "rev-parse", "HEAD")
    config = tmp_path / ".git/config"
    config.write_text(config.read_text() + "\n[credential]\n\thelper = malicious-task-helper\n")
    marker = tmp_path / "hook-ran"
    hook = tmp_path / ".git/hooks/pre-push"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    hook.chmod(0o700)
    before = config.read_bytes()
    pushes = []

    async def offline_git(directory: Path, *args: str, token: str | None = None) -> str:
        if args[0] == "push":
            assert directory != tmp_path and token == "test-only-not-a-real-credential"
            assert "malicious-task-helper" not in (directory / "config").read_text()
            assert not (directory / "hooks/pre-push").exists()
            pushes.append(args)
            return ""  # Only the remote write is mocked; init/object/fsck are real Git.
        return await original(directory, *args, token=token)

    monkeypatch.setattr(git_runner, "git", offline_git)
    monkeypatch.setenv("GITHUB_TOKEN", "test-only-not-a-real-credential")
    branch = f"agent/task-{uuid4()}"
    result = await git_runner.execute(
        git_runner.GitManifest(
            operation="publish",
            owner="fixture",
            repository="test",
            branch=branch,
            base_branch="main",
            expected_sha=sha,
        ),
        tmp_path,
    )
    assert result == {"head_sha": sha}
    assert pushes == [("push", "https://github.com/fixture/test.git", f"{sha}:refs/heads/{branch}")]
    assert config.read_bytes() == before and not marker.exists()


def test_object_transfer_rejects_symlinks_and_does_not_copy_alternates(tmp_path: Path) -> None:
    source, target = tmp_path / "objects", tmp_path / "copy"
    (source / "info").mkdir(parents=True)
    (source / "info/alternates").write_text("/untrusted/other-repository")
    git_runner.copy_objects(source, target)
    assert not (target / "info/alternates").exists()
    (source / "linked-object").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlinks"):
        git_runner.copy_objects(source, target)


@pytest.mark.asyncio
async def test_capture_bounds_output_and_does_not_leak_stderr(tmp_path: Path) -> None:
    assert await capture((sys.executable, "-c", "print('ok')"), cwd=tmp_path) == b"ok\n"
    with pytest.raises(RuntimeError, match="output bound"):
        await capture((sys.executable, "-c", "print('x'*1000000)"), output_limit=100)
    with pytest.raises(RuntimeError, match="raw stderr withheld") as error:
        await capture(
            (sys.executable, "-c", "import sys; sys.stderr.write('test-secret'); sys.exit(1)")
        )
    assert "test-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_capture_stops_on_timeout() -> None:
    with pytest.raises(TimeoutError):
        await capture((sys.executable, "-c", "import time; time.sleep(30)"), timeout=1)


@pytest.mark.asyncio
async def test_capture_drains_noisy_stderr_without_blocking_success():
    result = await capture(
        (sys.executable, "-c", "import sys; sys.stderr.write('x'*1000000); print('ok')"),
        output_limit=100,
        include_stderr=True,
        timeout=3,
    )
    assert result == b"ok\n"


@pytest.mark.asyncio
async def test_capture_keeps_bounded_failure_diagnostic():
    with pytest.raises(RuntimeError) as error:
        await capture(
            (sys.executable, "-c", "import sys; sys.stderr.write('x'*1000000); sys.exit(1)"),
            output_limit=100,
            include_stderr=True,
            timeout=3,
        )
    assert str(error.value) == "Operation failed: " + "x" * 100


@pytest.mark.asyncio
async def test_output_overflow_cleanup_does_not_compete_with_stderr_reader():
    with pytest.raises(RuntimeError, match="output bound"):
        await capture(
            (sys.executable, "-c", "import sys,time; print('x'*1000, flush=True); time.sleep(30)"),
            output_limit=100,
            include_stderr=True,
            timeout=3,
        )
