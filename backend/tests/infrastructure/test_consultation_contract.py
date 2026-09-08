from pathlib import Path
from uuid import uuid4

import pytest

from app.agent_runtime.infrastructure.container import RunnerMounts, developer_container_spec
from app.engineering.domain.consultation import outcome


def test_consultation_rejects_unbounded_or_unrecognized_output() -> None:
    assert outcome("PLAN_READY\nUse the current contract.", {"PLAN_READY"}) == (
        "PLAN_READY",
        "Use the current contract.",
    )
    assert len(outcome("PLAN_READY\n" + "x" * 30000, {"PLAN_READY"})[1]) == 7500
    for text in ("MERGED\nDone", "Guess"):
        with pytest.raises(ValueError):
            outcome(text, {"PLAN_READY"})


def test_helper_has_separate_native_home_and_read_only_checkout(tmp_path: Path) -> None:
    task_id, namespace = uuid4(), uuid4()
    workspace = tmp_path / "tasks" / str(task_id) / "repository"
    state = tmp_path / "native" / str(task_id) / "helpers" / str(namespace)
    control = tmp_path / "control" / str(task_id)
    for path in (workspace, state, control):
        path.mkdir(parents=True)
    (control / "workspace.lock").touch()
    (control / "task.json").touch()
    mounts = RunnerMounts(
        task_id,
        workspace,
        state,
        control / "task.json",
        tmp_path / "tasks",
        tmp_path / "native",
        tmp_path / "control",
        namespace,
    )
    spec = developer_container_spec(
        mounts,
        image="test:runner",
        network="private-providers",
        provider_environment={},
        read_only=True,
    )
    assert f"{workspace}:/workspace:ro" in spec["HostConfig"]["Binds"]
    assert f"{state}:/home/runner:rw" in spec["HostConfig"]["Binds"]
    with pytest.raises(ValueError, match="read-only"):
        developer_container_spec(
            mounts, image="test:runner", network="private-providers", provider_environment={}
        )
