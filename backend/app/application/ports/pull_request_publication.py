import uuid
from dataclasses import dataclass
from typing import Protocol


class PublishTaskNotFound(Exception):
    pass


class PublishConflict(Exception):
    pass


class PublishUnavailable(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PublishedPullRequest:
    number: int
    url: str
    state: str
    head_sha: str
    merged: bool
    merge_commit_sha: str | None


class PullRequestPublicationWorkflow(Protocol):
    async def publish(self, task_id: uuid.UUID) -> PublishedPullRequest: ...
