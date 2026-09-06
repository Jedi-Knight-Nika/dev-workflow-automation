from app.application.ports.job_completion import (
    FailedCompletionUnitOfWorkFactory,
    FailedJobCommand,
)
from app.domain.jobs import RetryPolicy
from app.domain.orchestration import RecoveryAction


class CompleteFailedJob:
    def __init__(
        self,
        unit_of_work_factory: FailedCompletionUnitOfWorkFactory,
        retry_policy: RetryPolicy,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._retry_policy = retry_policy

    async def execute(self, command: FailedJobCommand) -> bool:
        async with self._unit_of_work_factory() as unit_of_work:
            context = await unit_of_work.begin(command)
            if context is None:
                return False
            if context.manual_takeover:
                await unit_of_work.finish_during_takeover(context)
            elif context.recovery_action == RecoveryAction.WAIT_CONFIGURATION.value:
                await unit_of_work.wait(context, "WAITING_CONFIGURATION")
                await unit_of_work.raise_incident(context)
            elif context.recovery_action in {
                RecoveryAction.WAIT_HUMAN.value,
                RecoveryAction.STOP_SECURITY.value,
                RecoveryAction.FAIL_TERMINAL.value,
            }:
                await unit_of_work.wait(context, "WAITING_HUMAN")
                await unit_of_work.raise_incident(context)
            elif context.circuit_open:
                waiting_state = (
                    "WAITING_PROVIDER"
                    if context.recovery_action == RecoveryAction.WAIT_PROVIDER.value
                    else "WAITING_INTEGRATION"
                )
                await unit_of_work.wait(context, waiting_state)
                await unit_of_work.raise_incident(context)
            elif context.recovery_action != RecoveryAction.WORKFLOW.value and (
                self._retry_policy.should_retry(context.attempt)
            ):
                await unit_of_work.schedule_retry(
                    context,
                    self._retry_policy.delay_seconds(context.attempt),
                    self._retry_policy.max_attempts,
                )
            else:
                await unit_of_work.exhaust(context)
                await unit_of_work.raise_incident(context)
            await unit_of_work.commit()
            await unit_of_work.synchronize_tracker(context.task_id)
            return True
