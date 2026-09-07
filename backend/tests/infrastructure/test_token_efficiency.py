import copy
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Job, JobRole, Task
from app.infrastructure.workers.plan_reuse import plan_input_fingerprint
from app.infrastructure.workers.structured_output import ProviderAttempt
from app.providers import ProviderResponse
from app.worker import BudgetExceeded, enforce_spending_budget


@pytest.mark.parametrize("scope", ["job", "task"])
@pytest.mark.asyncio
async def test_budget_counts_prior_jobs_and_pending_calls(scope: str) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = None
    exhausted = SimpleNamespace(one=lambda: (399_990, 0, 2))
    empty = SimpleNamespace(one=lambda: (0, 0, 0))
    session.execute.side_effect = [exhausted] if scope == "job" else [empty, exhausted]
    job = Job(id=uuid.uuid4(), role=JobRole.THINKER, task_id=uuid.uuid4())
    task = Task(id=job.task_id, team_id=None)
    pending = [ProviderAttempt(ProviderResponse("{}", input_tokens=10, output_tokens=2), 1)]
    with pytest.raises(BudgetExceeded, match=f"{scope.title()} token budget exhausted"):
        await enforce_spending_budget(session, job, task, Settings(_env_file=None), {}, pending)


@pytest.mark.asyncio
async def test_missing_usage_still_counts_toward_model_call_limit() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = None
    session.execute.return_value = SimpleNamespace(one=lambda: (0, 0, 8))
    job = Job(id=uuid.uuid4(), role=JobRole.THINKER, task_id=uuid.uuid4())
    task = Task(id=job.task_id, team_id=None)
    with pytest.raises(BudgetExceeded, match="Job model-call budget exhausted"):
        await enforce_spending_budget(session, job, task, Settings(_env_file=None), {}, [])


def test_plan_fingerprint_ignores_bookkeeping_but_invalidates_material_changes() -> None:
    context = {
        "task": {"title": "Fix bug", "state": "NEW"},
        "job": {"id": "one", "action": "CREATE_PLAN", "payload": {}},
        "task_memory": {"memory_version": 1, "decisions": ["Keep API compatible"]},
        "previous_role_checkpoint": {"id": "old"},
    }
    runtime = {"model": "test", "system": "plan", "workflow_version": 1}
    workspaces = {"repo": "fingerprint-one"}
    original = copy.deepcopy(context)
    first = plan_input_fingerprint(context, runtime, workspaces)
    assert context == original
    context["job"]["id"] = "two"
    context["task"]["state"] = "PLANNING"
    context["task_memory"]["memory_version"] = 99
    context["previous_role_checkpoint"] = {"id": "new"}
    assert plan_input_fingerprint(context, runtime, workspaces) == first
    for changed_context, changed_runtime, changed_workspaces in [
        (
            {**context, "internal_task_conversation": [{"body": "New requirement"}]},
            runtime,
            workspaces,
        ),
        ({**context, "task": {"title": "Different task"}}, runtime, workspaces),
        (context, {**runtime, "workflow_version": 2}, workspaces),
        (context, {**runtime, "model": "different"}, workspaces),
        (context, runtime, {"repo": "new-file-content"}),
    ]:
        assert plan_input_fingerprint(changed_context, changed_runtime, changed_workspaces) != first


@pytest.mark.asyncio
async def test_legacy_memory_uses_latest_plan_without_erasing_history() -> None:
    from app.db.models import TaskMemory
    from app.infrastructure.persistence.task_memory import TaskMemoryService

    task = Task(id=uuid.uuid4(), title="Fix bug")
    old_decisions = [f"Preserve behavior phrased version {i}" for i in range(100)]
    record = TaskMemory(
        task_id=task.id,
        goal=task.title,
        decisions=old_decisions,
        known_facts=[],
        rejected_approaches=[],
        invariants=[],
        important_files=[],
        important_symbols=[],
        open_questions=[],
        open_finding_ids=[],
        resolved_finding_summaries=[],
        version=33,
        current_plan_job_id=uuid.uuid4(),
    )
    plan = Job(
        result={
            "data": {
                "result": "PLAN_READY",
                "constraints": ["Preserve behavior"],
                "targets": ["module.py"],
            }
        }
    )
    session = AsyncMock(spec=AsyncSession)
    session.get.side_effect = [record, plan]
    snapshot = await TaskMemoryService(session).load(task)
    assert snapshot.decisions == ("Preserve behavior",)
    assert len(json.dumps(snapshot.decisions)) < len(json.dumps(old_decisions)) / 50
    assert record.decisions == old_decisions
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_plan_reuse_rejects_dirty_checkout_and_uses_actual_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.infrastructure.workers.plan_reuse import clean_workspace_revisions

    git = AsyncMock(side_effect=["", "actual-head"])
    monkeypatch.setattr("app.infrastructure.workers.plan_reuse.run_git", git)
    assert await clean_workspace_revisions([("repo", Path("/repo"))]) == {"repo": "actual-head"}
    for status in [" M file.py", "M  file.py", "?? new.py"]:
        git.side_effect = [status]
        assert await clean_workspace_revisions([("repo", Path("/repo"))]) is None
