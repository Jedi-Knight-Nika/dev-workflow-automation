import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "mode,overlays",
    [
        ("console", []),
        ("execution", ["deploy/compose.execution.yaml"]),
        ("full", ["deploy/compose.execution.yaml", "deploy/compose.observability.yaml"]),
    ],
)
def test_launcher_selects_explicit_modes_without_starting_docker(tmp_path, mode, overlays):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    launcher = scripts / "start-local.sh"
    shutil.copyfile(Path(__file__).parents[3] / "scripts/start-local.sh", launcher)
    shutil.copyfile(
        Path(__file__).parents[3] / "scripts/ensure-rabbitmq-env.sh",
        scripts / "ensure-rabbitmq-env.sh",
    )
    (tmp_path / ".env").write_text("")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text('#!/bin/sh\n[ "$1" = volume ] && exit 0\nprintf "%s\\n" "$@"\n')
    docker.chmod(0o755)
    result = subprocess.run(
        ["sh", str(launcher), "--mode", mode, "--no-build"],
        env={**os.environ, "PATH": f"{binaries}:{os.defpath}"},
        capture_output=True,
        text=True,
        check=True,
    )
    arguments = result.stdout.splitlines()
    assert "compose.yaml" in arguments
    assert "--no-build" in arguments
    assert "--build" not in arguments
    for overlay in ("deploy/compose.execution.yaml", "deploy/compose.observability.yaml"):
        assert (overlay in arguments) == (overlay in overlays)
    invalid = subprocess.run(
        ["sh", str(launcher), "--mode", "unknown"], capture_output=True, text=True, check=False
    )
    assert invalid.returncode == 2
