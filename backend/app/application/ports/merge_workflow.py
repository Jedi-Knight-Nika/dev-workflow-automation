import uuid
from dataclasses import dataclass
from typing import Protocol

from app.domain.pull_requests import ValidationEvidence


@dataclass(frozen=True, slots=True)
class MergeContext:
    task_id: uuid.UUID
    repository_id: uuid.UUID
    owner: str
    repository: str
    pull_request_number: int
    expected_revision: str
    evidence: list[ValidationEvidence]


@dataclass(frozen=True, slots=True)
class MergeOutcome:
    merged: bool
    sha: str | None
    message: str


class MergeWorkflow(Protocol):
    async def load_context(self, task_id: uuid.UUID) -> MergeContext | None: ...

    async def current_head(self, context: MergeContext) -> str: ...

    async def reject_stale_head(self, context: MergeContext, actual_revision: str) -> None: ...

    async def merge(self, context: MergeContext) -> MergeOutcome: ...

    async def complete(self, context: MergeContext, outcome: MergeOutcome) -> None: ...

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None: ...

    async def rollback(self) -> None: ...
