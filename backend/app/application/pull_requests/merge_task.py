import uuid

from app.application.ports.merge_workflow import MergeOutcome, MergeWorkflow
from app.domain.pull_requests import assert_merge_gates


class MergeTaskNotFound(LookupError):
    pass


class MergeUnavailable(RuntimeError):
    pass


class MergeConflict(RuntimeError):
    pass


class MergeTask:
    def __init__(self, workflow: MergeWorkflow) -> None:
        self._workflow = workflow

    async def execute(self, task_id: uuid.UUID) -> MergeOutcome:
        try:
            context = await self._workflow.load_context(task_id)
            if context is None:
                raise MergeTaskNotFound("Task not found")
            assert_merge_gates(context.evidence)
            actual_revision = await self._workflow.current_head(context)
            if actual_revision != context.expected_revision:
                await self._workflow.reject_stale_head(context, actual_revision)
                raise MergeConflict("PR head changed; validations are stale")
            outcome = await self._workflow.merge(context)
            if not outcome.merged:
                raise MergeConflict(outcome.message)
            await self._workflow.complete(context, outcome)
        except (MergeConflict, MergeTaskNotFound, ValueError):
            raise
        except Exception as exc:
            await self._workflow.rollback()
            raise MergeUnavailable(f"GitHub merge failed: {exc}") from exc
        await self._workflow.synchronize_tracker(task_id)
        return outcome
