import uuid

from app.application.ports.pull_request_publication import (
    PublishedPullRequest,
    PullRequestPublicationWorkflow,
)


class PublishTaskPullRequest:
    def __init__(self, workflow: PullRequestPublicationWorkflow) -> None:
        self._workflow = workflow

    async def execute(self, task_id: uuid.UUID) -> PublishedPullRequest:
        return await self._workflow.publish(task_id)
