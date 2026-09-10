from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.infrastructure.lease_guard import assert_current
from app.engineering.infrastructure.task_models import Job, Task
from app.platform.scheduling.states import JobState
from app.supervisor.infrastructure.localization import candidate_paths
from app.supervisor.infrastructure.schemas import SupervisorDecision


def test_empty_localization_does_not_scan_workspace(tmp_path, monkeypatch):
    def unexpected_walk(*args, **kwargs):
        raise AssertionError("No search terms should mean no filesystem scan")

    monkeypatch.setattr("app.supervisor.infrastructure.localization.os.walk", unexpected_walk)
    assert candidate_paths(tmp_path, "?!") == []


def test_supervisor_cannot_authorize_merge_or_freeform_commands() -> None:
    with pytest.raises(ValidationError):
        SupervisorDecision(
            action="MERGE",
            task_class="TINY",
            confidence=1,
            assessment="ok",
            execution_brief="",
            acceptance_criteria=[],
            unresolved_items=[],
        )


def test_suspended_or_expired_lease_rejects_decision() -> None:
    task = Task(id=uuid4(), status="ACTIVE", lifecycle_version=3, manual_takeover=False)
    lease = PhaseLease(uuid4(), task.id, uuid4(), "DEVELOPER_TURN", 3)
    job = Job(
        id=lease.job_id,
        task_id=task.id,
        state=JobState.RUNNING,
        lease_token=lease.token,
        lease_expires_at=datetime.now(UTC) + timedelta(seconds=30),
    )
    assert_current(job, task, lease)
    task.status = "PAUSED"
    with pytest.raises(PhaseBlocked):
        assert_current(job, task, lease)
    task.status = "ACTIVE"
    job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(PhaseBlocked):
        assert_current(job, task, lease)


def test_filename_hints_ignore_dependencies_and_symlinks(tmp_path: Path) -> None:
    (tmp_path / "LiveExecution.svelte").touch()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "LiveExecution.js").touch()
    (tmp_path / "LiveExecution-link").symlink_to(
        tmp_path / "node_modules", target_is_directory=True
    )
    assert candidate_paths(tmp_path, "LIVE EXECUTION გადაადგილება") == ["LiveExecution.svelte"]
