import uuid

import pytest

from app.application.ports.pull_request_publication import PublishedPullRequest
from app.application.pull_requests import PublishTaskPullRequest


class FakePublicationWorkflow:
    def __init__(self, result: PublishedPullRequest) -> None:
        self.result = result
        self.task_id: uuid.UUID | None = None

    async def publish(self, task_id: uuid.UUID) -> PublishedPullRequest:
        self.task_id = task_id
        return self.result


@pytest.mark.asyncio
async def test_publish_task_pull_request_delegates_through_port() -> None:
    task_id = uuid.uuid4()
    published = PublishedPullRequest(42, "https://example.test/pr/42", "open", "abc", False, None)
    workflow = FakePublicationWorkflow(published)

    result = await PublishTaskPullRequest(workflow).execute(task_id)

    assert result is published
    assert workflow.task_id == task_id
