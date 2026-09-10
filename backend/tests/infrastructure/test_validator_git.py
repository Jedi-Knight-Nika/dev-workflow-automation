from unittest.mock import AsyncMock

import pytest

from app.engineering.infrastructure import validator_runner


def test_configured_git_checks_use_workspace_trust():
    argv = validator_runner.validation_argv(["git", "diff", "--check"])
    assert "safe.directory=/workspace" in argv
    assert argv[-2:] == ("diff", "--check")
    assert validator_runner.validation_argv(["npm", "test"]) == ("npm", "test")


@pytest.mark.asyncio
async def test_validator_git_trusts_only_mounted_workspace(monkeypatch):
    capture = AsyncMock(return_value=b"agent/task-test\n")
    monkeypatch.setattr(validator_runner, "capture", capture)
    assert await validator_runner.git("branch", "--show-current") == "agent/task-test"
    argv = capture.call_args.args[0]
    assert "safe.directory=/workspace" in argv
    assert "safe.directory=*" not in argv
    assert "core.hooksPath=/dev/null" in argv
    capture.side_effect = RuntimeError("sensitive subprocess output")
    with pytest.raises(
        validator_runner.ValidatorGitError, match="Validator Git operation failed"
    ) as error:
        await validator_runner.git("status")
    assert "sensitive" not in str(error.value)
