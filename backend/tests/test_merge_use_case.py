import uuid

import pytest

from app.application.ports.merge_workflow import MergeContext, MergeOutcome
from app.application.pull_requests import MergeConflict, MergeTask, MergeTaskNotFound
from app.domain.pull_requests import MergeGateRejected, ValidationEvidence, assert_merge_gates


def context(evidence: list[ValidationEvidence] | None = None) -> MergeContext:
    return MergeContext(
        task_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        owner="citycom",
        repository="service",
        pull_request_number=42,
        expected_revision="expected-sha",
        evidence=evidence or [ValidationEvidence("CHECK", "tests", "SUCCESS")],
    )


class FakeMergeWorkflow:
    def __init__(self, merge_context: MergeContext | None) -> None:
        self.context = merge_context
        self.head = merge_context.expected_revision if merge_context else ""
        self.outcome = MergeOutcome(True, "merge-sha", "merged")
        self.stale: str | None = None
        self.completed = False
        self.synchronized = False
        self.rolled_back = False

    async def load_context(self, _task_id: uuid.UUID) -> MergeContext | None:
        return self.context

    async def current_head(self, _context: MergeContext) -> str:
        return self.head

    async def reject_stale_head(self, _context: MergeContext, actual_revision: str) -> None:
        self.stale = actual_revision

    async def merge(self, _context: MergeContext) -> MergeOutcome:
        return self.outcome

    async def complete(self, _context: MergeContext, _outcome: MergeOutcome) -> None:
        self.completed = True

    async def synchronize_tracker(self, _task_id: uuid.UUID) -> None:
        self.synchronized = True

    async def rollback(self) -> None:
        self.rolled_back = True


def test_merge_gate_requires_ci_and_rejects_latest_blocking_evidence() -> None:
    with pytest.raises(MergeGateRejected, match="no completed CI"):
        assert_merge_gates([ValidationEvidence("REVIEW", "reviewer", "APPROVED")])
    with pytest.raises(MergeGateRejected, match="failing gates"):
        assert_merge_gates(
            [
                ValidationEvidence("CHECK", "tests", "SUCCESS"),
                ValidationEvidence("REVIEW", "reviewer", "CHANGES_REQUESTED"),
            ]
        )


@pytest.mark.asyncio
async def test_merge_use_case_completes_then_synchronizes_tracker() -> None:
    workflow = FakeMergeWorkflow(context())

    result = await MergeTask(workflow).execute(workflow.context.task_id)  # type: ignore[union-attr,arg-type]

    assert result.sha == "merge-sha"
    assert workflow.completed
    assert workflow.synchronized
    assert not workflow.rolled_back


@pytest.mark.asyncio
async def test_merge_use_case_persists_stale_head_and_stops() -> None:
    workflow = FakeMergeWorkflow(context())
    workflow.head = "new-head"

    with pytest.raises(MergeConflict, match="validations are stale"):
        await MergeTask(workflow).execute(workflow.context.task_id)  # type: ignore[union-attr,arg-type]

    assert workflow.stale == "new-head"
    assert not workflow.completed
    assert not workflow.synchronized


@pytest.mark.asyncio
async def test_merge_use_case_reports_missing_task() -> None:
    workflow = FakeMergeWorkflow(None)

    with pytest.raises(MergeTaskNotFound):
        await MergeTask(workflow).execute(uuid.uuid4())  # type: ignore[arg-type]
