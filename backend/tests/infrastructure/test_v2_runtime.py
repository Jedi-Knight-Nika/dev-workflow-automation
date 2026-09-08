import hashlib
import hmac
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.infrastructure.container import (
    RunnerMounts,
    developer_container_spec,
    validation_container_spec,
)
from app.engineering.infrastructure.validation import run_check
from app.intake.infrastructure.slack import verify_slack_signature


def mounts(tmp_path: Path) -> RunnerMounts:
    task_id = uuid4()
    workspace = tmp_path / "tasks" / str(task_id) / "repo"
    state = tmp_path / "state" / str(task_id)
    workspace.mkdir(parents=True)
    state.mkdir(parents=True)
    manifest = tmp_path / "control" / str(task_id) / "job" / "task.json"
    manifest.parent.mkdir(parents=True)
    (manifest.parent.parent / "workspace.lock").touch()
    manifest.write_text("{}")
    return RunnerMounts(
        task_id,
        workspace,
        state,
        manifest,
        tmp_path / "tasks",
        tmp_path / "state",
        tmp_path / "control",
    )


def test_runner_only_mounts_task_worktree_and_private_native_state(tmp_path: Path) -> None:
    paths = mounts(tmp_path)
    spec = developer_container_spec(
        paths,
        image="runner:pinned",
        network="provider-egress",
        provider_environment={"OPENAI_API_KEY": "test"},
    )
    assert spec["User"] == "10001:10001"
    assert len(spec["HostConfig"]["Binds"]) == 4
    assert all("docker.sock" not in value for value in spec["HostConfig"]["Binds"])
    assert spec["HostConfig"]["ReadonlyRootfs"] is True
    assert not any("DATABASE" in value or "GITHUB" in value for value in spec["Env"])


def test_validation_has_no_native_state_network_or_credentials(tmp_path: Path) -> None:
    paths = mounts(tmp_path)
    spec = validation_container_spec(paths, image="runner:pinned")
    assert spec["HostConfig"]["NetworkMode"] == "none"
    assert len(spec["HostConfig"]["Binds"]) == 3
    assert all(str(paths.state) not in value for value in spec["HostConfig"]["Binds"])
    assert "/home/runner" in spec["HostConfig"]["Tmpfs"]
    assert not any("KEY=" in value or "TOKEN=" in value for value in spec["Env"])


def test_runner_rejects_shared_mounts_secrets_and_host_network(tmp_path: Path) -> None:
    paths = mounts(tmp_path)
    for invalid in (
        replace(paths, workspace=paths.tasks_root),
        replace(paths, state=paths.state_root),
    ):
        with pytest.raises(ValueError):
            invalid.validate()
    with pytest.raises(ValueError):
        developer_container_spec(
            paths, image="runner:pinned", network="host", provider_environment={}
        )
    with pytest.raises(ValueError):
        developer_container_spec(
            paths,
            image="runner:pinned",
            network="provider-egress",
            provider_environment={"GITHUB_TOKEN": "secret"},
        )


def test_runner_rejects_symlink_escape(tmp_path: Path) -> None:
    paths = mounts(tmp_path)
    link = paths.workspace.parent / "escape"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        replace(paths, workspace=link).validate()


def test_runner_cannot_write_its_own_authorization(tmp_path: Path) -> None:
    paths = mounts(tmp_path)
    unsafe = paths.state / "task.json"
    unsafe.write_text("{}")
    with pytest.raises(ValueError):
        replace(paths, manifest=unsafe).validate()


def test_slack_verification_rejects_tamper_and_replay() -> None:
    body, timestamp, secret = b'{"event_id":"event-1"}', "1000", "test-signing-secret"
    signature = "v0=" + hmac.new(secret.encode(), b"v0:1000:" + body, hashlib.sha256).hexdigest()
    assert verify_slack_signature(
        body=body, timestamp=timestamp, signature=signature, secret=secret, now=1001
    )
    assert not verify_slack_signature(
        body=body + b" ", timestamp=timestamp, signature=signature, secret=secret, now=1001
    )
    assert not verify_slack_signature(
        body=body, timestamp=timestamp, signature=signature, secret=secret, now=1301
    )


@pytest.mark.asyncio
async def test_validation_is_real_subprocess_and_output_is_bounded(tmp_path: Path) -> None:
    result = await run_check(
        (sys.executable, "-c", "print('x'*20000)"), workspace=tmp_path, output_limit=100
    )
    assert result.passed
    assert result.started_at and result.finished_at and result.started_at <= result.finished_at
    assert len(result.output_tail.encode()) == 100
    failed = await run_check((sys.executable, "-c", "raise SystemExit(2)"), workspace=tmp_path)
    assert not failed.passed
    assert failed.exit_code == 2


@pytest.mark.asyncio
async def test_codex_uses_pinned_sdk_resume_and_native_sandbox(tmp_path: Path) -> None:
    sdk = pytest.importorskip("openai_codex")
    from app.agent_runtime.infrastructure.codex import CodexHarness

    client = AsyncMock()
    client.thread_resume.return_value.id = "thread-1"
    with patch.object(sdk, "AsyncCodex", return_value=client):
        harness = CodexHarness(HarnessSettings("gpt-5.6-terra", tmp_path, "contract"))
        await harness.resume("thread-1")
        options = client.thread_resume.await_args.kwargs
        assert client.thread_resume.await_args.args == ("thread-1",)
        assert options["model"] == "gpt-5.6-terra"
        assert options["sandbox"] == sdk.Sandbox.workspace_write
        assert options["approval_mode"] == sdk.ApprovalMode.deny_all
        assert options["config"]["features.multi_agent"] is False
        client.thread_start.assert_not_called()
        await harness.close()


@pytest.mark.asyncio
async def test_claude_permission_and_explicit_resume(tmp_path: Path) -> None:
    sdk = pytest.importorskip("claude_agent_sdk")
    from app.agent_runtime.infrastructure.claude import ClaudeHarness

    client = AsyncMock()
    with patch.object(sdk, "ClaudeSDKClient", return_value=client) as factory:
        harness = ClaudeHarness(HarnessSettings("claude-sonnet-5", tmp_path, "contract"))
        await harness.resume("session-1")
        options = factory.call_args.args[0]
        assert options.resume == "session-1"
        assert not options.continue_conversation
        assert "Agent" in options.disallowed_tools
        assert options.permission_mode != "bypassPermissions"
        assert isinstance(
            await harness._permission("Write", {"file_path": "/etc/hosts"}, None),
            sdk.PermissionResultDeny,
        )
        assert isinstance(await harness._permission("Agent", {}, None), sdk.PermissionResultDeny)
        await harness.close()
