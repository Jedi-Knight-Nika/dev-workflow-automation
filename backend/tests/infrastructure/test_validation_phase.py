from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.agent_runtime.infrastructure.models import DeveloperSession
from app.engineering.application.jobs import PhaseBlocked
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure import validation_phase
from app.engineering.infrastructure.task_models import Task


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["passed", "failed", "repeated", "review_changes"])
async def test_validation_preserves_evidence_feedback_and_review_order(
    tmp_path, monkeypatch, outcome
):
    passed = outcome in {"passed", "review_changes"}
    sha = "a" * 40
    task = SimpleNamespace(
        id=uuid4(),
        repository_id=uuid4(),
        branch_name=f"agent/task-{uuid4()}",
        title="Fix panel",
        requirement_version=1,
        lifecycle_version=1,
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
            "passed": passed,
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
        assert len(evidence) == 1
        assert evidence[0].head_sha == sha
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
    if outcome == "repeated":
        with pytest.raises(PhaseBlocked, match="Repeated validation failure"):
            await validation_phase.validate_phase(*args)
    else:
        result = await validation_phase.validate_phase(*args)
        assert result == (
            Action.VALIDATION_PASSED if outcome == "passed" else Action.VALIDATION_FAILED
        )
    assert task.current_revision == sha
    if passed:
        assert native.checkpoint["publication_checks"] == commands
        assert events == ["validate", "persisted", "review"]
    else:
        assert "check evidence" in native.checkpoint["next_feedback"]
        assert events == ["validate", "persisted"]
    assert save_review.await_count == int(outcome == "review_changes")
