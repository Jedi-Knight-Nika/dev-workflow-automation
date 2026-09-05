import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class TaskState(StrEnum):
    NEW = "NEW"
    CONTEXT_PENDING = "CONTEXT_PENDING"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    QUEUED_FOR_EXECUTION = "QUEUED_FOR_EXECUTION"
    IMPLEMENTING = "IMPLEMENTING"
    LOCAL_VALIDATION = "LOCAL_VALIDATION"
    INTERNAL_REVIEW = "INTERNAL_REVIEW"
    WAITING_GITHUB = "WAITING_GITHUB"
    READY_TO_MERGE = "READY_TO_MERGE"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    MERGED = "MERGED"


@dataclass(slots=True)
class Task:
    id: uuid.UUID
    title: str
    description: str
    priority: int
    state: TaskState
    external_key: str | None
    repository_id: uuid.UUID | None
    current_revision: str | None
    branch_name: str | None
    workspace_path: str | None
    pull_request_number: int | None
    pull_request_url: str | None
    manual_takeover: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        title: str,
        description: str = "",
        priority: int = 3,
        external_key: str | None = None,
        repository_id: uuid.UUID | None = None,
        now: datetime | None = None,
        task_id: uuid.UUID | None = None,
    ) -> "Task":
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("Task title cannot be blank")
        if not 0 <= priority <= 5:
            raise ValueError("Task priority must be between 0 and 5")
        created_at = now or datetime.now(UTC)
        return cls(
            id=task_id or uuid.uuid4(),
            title=normalized_title,
            description=description,
            priority=priority,
            state=TaskState.NEW,
            external_key=external_key,
            repository_id=repository_id,
            current_revision=None,
            branch_name=None,
            workspace_path=None,
            pull_request_number=None,
            pull_request_url=None,
            manual_takeover=False,
            created_at=created_at,
            updated_at=created_at,
        )
