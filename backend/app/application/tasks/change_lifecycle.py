import uuid

from app.application.ports.task_lifecycle import TaskLifecycleUnitOfWorkFactory
from app.domain.tasks import LifecycleAction, Task, lifecycle_directive


class TaskNotFound(Exception):
    pass


class ChangeTaskLifecycle:
    def __init__(self, unit_of_work_factory: TaskLifecycleUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(self, task_id: uuid.UUID, action: LifecycleAction) -> Task:
        async with self._unit_of_work_factory() as unit_of_work:
            context = await unit_of_work.load(task_id)
            if context is None:
                raise TaskNotFound("Task not found")
            directive = lifecycle_directive(
                action,
                current_state=context.state,
                manual_takeover=context.manual_takeover,
                has_pull_request=context.has_pull_request,
            )
            revision = fingerprint = None
            if action == LifecycleAction.RESUME and context.has_workspace:
                revision, fingerprint = await unit_of_work.refresh_workspace(task_id)
            task = await unit_of_work.apply(
                context, directive, revision=revision, workspace_fingerprint=fingerprint
            )
            await unit_of_work.commit()
            return task
