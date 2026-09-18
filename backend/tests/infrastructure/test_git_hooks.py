import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def hook_repository(tmp_path):
    root = Path(__file__).parents[3]
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], env=environment, check=True)
    hooks = tmp_path / ".githooks"
    hooks.mkdir()
    shutil.copyfile(root / ".githooks/pre-push", hooks / "pre-push")
    shutil.copyfile(root / "Makefile", tmp_path / "Makefile")
    return tmp_path, environment


@pytest.mark.parametrize("exit_code", [0, 23])
def test_installed_pre_push_runs_root_checks_and_propagates_failure(hook_repository, exit_code):
    repository, environment = hook_repository
    subprocess.run(["make", "hooks"], cwd=repository, env=environment, check=True)
    assert os.access(repository / ".githooks/pre-push", os.X_OK)
    binaries = repository / "bin"
    binaries.mkdir()
    make = binaries / "make"
    make.write_text(
        f'#!/bin/sh\npwd > hook-directory\nprintf "%s\\n" "$@" > hook-arguments\nexit {exit_code}\n'
    )
    make.chmod(0o755)
    nested = repository / "nested"
    nested.mkdir()
    result = subprocess.run(
        ["git", "hook", "run", "pre-push"],
        cwd=nested,
        env={**environment, "PATH": f"{binaries}:{environment['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == exit_code
    assert Path((repository / "hook-directory").read_text().strip()) == repository.resolve()
    assert (repository / "hook-arguments").read_text() == "pre-push\n"


def test_hook_installation_preserves_a_custom_hooks_path(hook_repository):
    repository, environment = hook_repository
    subprocess.run(
        ["git", "config", "--local", "core.hooksPath", "custom-hooks"],
        cwd=repository,
        env=environment,
        check=True,
    )
    result = subprocess.run(
        ["make", "hooks"],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Existing core.hooksPath=custom-hooks" in result.stderr
    configured = subprocess.check_output(
        ["git", "config", "--get", "core.hooksPath"], cwd=repository, env=environment, text=True
    )
    assert configured.strip() == "custom-hooks"
