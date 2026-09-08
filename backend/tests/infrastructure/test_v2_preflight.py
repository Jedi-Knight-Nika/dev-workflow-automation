from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.agent_runtime.application.harness import WorkspaceUnavailable
from app.agent_runtime.infrastructure import preflight
from app.agent_runtime.infrastructure.runner import Manifest, execute


@pytest.mark.asyncio
async def test_runner_checks_workspace_before_constructing_or_authenticating_harness() -> None:
    manifest = Manifest(harness="codex", model="unused", prompt="unused", max_cost_usd="1")
    with (
        patch("os.getuid", return_value=10001),
        patch("pathlib.Path.cwd", return_value=Path("/workspace")),
        patch.dict("os.environ", {}, clear=True),
        patch(
            "app.agent_runtime.infrastructure.runner.check_workspace",
            side_effect=WorkspaceUnavailable("Bad ownership"),
        ) as check,
        pytest.raises(WorkspaceUnavailable, match="Bad ownership"),
    ):
        await execute(manifest)
    check.assert_awaited_once_with(Path("/workspace"), read_only=False)


@pytest.mark.asyncio
async def test_preflight_has_no_credentials_or_persistent_git_configuration(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    with patch.object(preflight, "capture", new_callable=AsyncMock) as capture:
        capture.return_value = str(tmp_path).encode()
        await preflight.check_workspace(tmp_path)
    assert capture.await_args.kwargs["env"]["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert not any("KEY" in key or "TOKEN" in key for key in capture.await_args.kwargs["env"])
    assert "config" not in capture.await_args.args[0]


@pytest.mark.asyncio
async def test_preflight_rejects_missing_git_and_sanitizes_git_errors(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceUnavailable):
        await preflight.check_workspace(tmp_path)
    (tmp_path / ".git").mkdir()
    with (
        patch.object(preflight, "capture", side_effect=RuntimeError("sensitive details")),
        pytest.raises(WorkspaceUnavailable, match="UID 10001") as error,
    ):
        await preflight.check_workspace(tmp_path)
    assert "sensitive" not in str(error.value)
