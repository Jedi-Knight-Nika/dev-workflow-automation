from app.application.ports.job_enqueueing import (
    EnqueuedJob,
    EnqueueJobCommand,
    JobEnqueueWorkflow,
)


class EnqueueTaskJob:
    def __init__(self, workflow: JobEnqueueWorkflow) -> None:
        self._workflow = workflow

    async def execute(self, command: EnqueueJobCommand) -> EnqueuedJob:
        return await self._workflow.enqueue(command)
