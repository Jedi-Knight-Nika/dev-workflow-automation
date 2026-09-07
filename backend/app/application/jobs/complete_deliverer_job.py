from app.application.ports.deliverer_completion import (
    DelivererCompletionCommand,
    DelivererCompletionUnitOfWorkFactory,
)
from app.domain.jobs import success_directive


class CompleteDelivererJob:
    def __init__(self, unit_of_work_factory: DelivererCompletionUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(self, command: DelivererCompletionCommand) -> bool:
        async with self._unit_of_work_factory() as unit_of_work:
            context = await unit_of_work.begin(command)
            if context is None:
                return False
            if context.manual_takeover:
                await unit_of_work.finish_during_takeover(context)
            elif context.action == "RESPOND_TO_MESSAGE":
                await unit_of_work.finish_conversation(context)
            else:
                directive = success_directive(
                    role="DELIVERER",
                    action=context.action,
                    outcome=context.outcome,
                    data=context.data,
                )
                await unit_of_work.apply(context, directive)
            await unit_of_work.commit()
            if not context.manual_takeover and context.action != "RESPOND_TO_MESSAGE":
                await unit_of_work.execute_external_delivery_actions(context)
            await unit_of_work.synchronize_tracker(context.task_id)
            return True
