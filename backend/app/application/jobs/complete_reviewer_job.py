from app.application.ports.reviewer_completion import (
    ReviewerCompletionCommand,
    ReviewerCompletionUnitOfWorkFactory,
)
from app.domain.jobs import success_directive


class CompleteReviewerJob:
    def __init__(
        self,
        unit_of_work_factory: ReviewerCompletionUnitOfWorkFactory,
        max_same_finding_repeats: int,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._max_same_finding_repeats = max_same_finding_repeats

    async def execute(self, command: ReviewerCompletionCommand) -> bool:
        async with self._unit_of_work_factory() as unit_of_work:
            context = await unit_of_work.begin(command)
            if context is None:
                return False
            should_publish = False
            if context.manual_takeover:
                await unit_of_work.finish_during_takeover(context)
            else:
                should_publish = await unit_of_work.apply(
                    context,
                    success_directive(
                        role="REVIEWER",
                        action=context.action,
                        outcome=context.outcome,
                        data=context.data,
                        repeat_count=context.repeat_count,
                        max_same_finding_repeats=self._max_same_finding_repeats,
                    ),
                )
            await unit_of_work.commit()
            if should_publish:
                await unit_of_work.publish(context.task_id)
            else:
                await unit_of_work.synchronize_tracker(context.task_id)
            return True
