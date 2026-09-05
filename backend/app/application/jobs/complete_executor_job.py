from app.application.ports.executor_completion import (
    ExecutorCompletionCommand,
    ExecutorCompletionUnitOfWorkFactory,
)
from app.domain.jobs import success_directive


class CompleteExecutorJob:
    def __init__(self, unit_of_work_factory: ExecutorCompletionUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(self, command: ExecutorCompletionCommand) -> bool:
        async with self._unit_of_work_factory() as unit_of_work:
            context = await unit_of_work.begin(command)
            if context is None:
                return False
            if context.manual_takeover:
                await unit_of_work.finish_during_takeover(context)
            else:
                await unit_of_work.apply(
                    context,
                    success_directive(
                        role="EXECUTOR",
                        action=context.action,
                        outcome=context.outcome,
                        data=context.data,
                    ),
                )
            await unit_of_work.commit()
            await unit_of_work.synchronize_tracker(context.task_id)
            return True
