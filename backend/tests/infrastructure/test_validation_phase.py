from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.agent_runtime.infrastructure.models import DeveloperSession
from app.engineering.application.jobs import PhaseBlocked
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure import validation_phase
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.task_models import Task, TaskEvent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    ["passed", "failed", "repeated", "review_changes", "stale", "commit_failure", "truthy"],
)
async def test_validation_preserves_evidence_feedback_and_review_order(
    tmp_path, monkeypatch, outcome
):
    passed = outcome in {"passed", "review_changes", "stale", "commit_failure"}
    sha = "a" * 40
    task = SimpleNamespace(
        id=uuid4(),
        repository_id=uuid4(),
        branch_name=f"agent/task-{uuid4()}",
        title="Fix panel",
        requirement_version=1,
        lifecycle_version=2 if outcome == "stale" else 1,
        no_progress_count=1 if outcome == "repeated" else 0,
        progress_fingerprint={"validation": "same"},
        current_revision=None,
    )
    native = SimpleNamespace(id=uuid4(), checkpoint={"base_sha": sha}, workspace_path=str(tmp_path))
    lease = SimpleNamespace(job_id=uuid4(), token=uuid4(), lifecycle_version=1)
    evidence, events = [], []

    async def get(model, *args, **kwargs):
        return task if model is Task else native if model is DeveloperSession else None

    session = SimpleNamespace(get=get, add=evidence.append)

    @asynccontextmanager
    async def read():
        yield session

    @asynccontextmanager
    async def transaction():
        yield session
        if outcome == "commit_failure":
            raise RuntimeError("Evidence commit failed")
        events.append("persisted")

    sessions = Mock(side_effect=read)
    sessions.begin = transaction
    commands = [["check"]]
    settings = SimpleNamespace(
        repository_validation_commands={str(task.repository_id): commands},
        developer_turn_timeout_seconds=30,
        developer_container_image="validator",
    )

    async def run(*args):
        events.append("validate")
        return {
            "passed": "true" if outcome == "truthy" else passed,
            "head_sha": sha,
            "fingerprint": "same",
            "checks": [
                {
                    "command": ["check"],
                    "exit_code": 0 if passed else 1,
                    "timed_out": False,
                    "output_tail": "check evidence",
                }
            ],
        }

    async def review(*args, **kwargs):
        assert events == ["validate", "persisted"]
        checks = [item for item in evidence if isinstance(item, ValidationRun)]
        assert len(checks) == 1 and checks[0].head_sha == sha
        events.append("review")
        return ("REVIEW_CHANGES", "Fix details") if outcome == "review_changes" else None

    monkeypatch.setattr(
        validation_phase,
        "phase_mounts",
        lambda *a: SimpleNamespace(manifest=tmp_path / "task.json"),
    )
    monkeypatch.setattr(
        validation_phase, "validation_container_spec", lambda *a, **kw: {"Labels": {}}
    )
    monkeypatch.setattr(validation_phase, "run_container_job", run)
    monkeypatch.setattr(validation_phase, "consult", review)
    save_review = AsyncMock()
    monkeypatch.setattr(validation_phase, "save_consultation_feedback", save_review)
    args = (sessions, settings, None, lease, task, native, SimpleNamespace(name="Team"))
    if outcome in {"stale", "commit_failure"}:
        error = ValueError if outcome == "stale" else RuntimeError
        with pytest.raises(error):
            await validation_phase.validate_phase(*args)
        assert events == ["validate"]
        save_review.assert_not_awaited()
        if outcome == "stale":
            assert evidence == [] and native.checkpoint == {"base_sha": sha}
        return
    if outcome == "repeated":
        with pytest.raises(PhaseBlocked, match="Repeated validation failure"):
            await validation_phase.validate_phase(*args)
    else:
        result = await validation_phase.validate_phase(*args)
        assert result == (
            Action.VALIDATION_PASSED if outcome == "passed" else Action.VALIDATION_FAILED
        )
    batches = [item for item in evidence if isinstance(item, TaskEvent)]
    assert len(batches) == 1 and batches[0].payload["passed"] == passed
    assert batches[0].payload["requirement_version"] == 1
    assert task.current_revision == sha
    if passed:
        assert native.checkpoint["publication_checks"] == commands
        assert events == ["validate", "persisted", "review"]
    else:
        assert "check evidence" in native.checkpoint["next_feedback"]
        assert events == ["validate", "persisted"]
    assert save_review.await_count == int(outcome == "review_changes")
