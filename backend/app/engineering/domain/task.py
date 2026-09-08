import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.engineering.domain.lifecycle import Stage, TaskStatus, WaitReason


@dataclass(slots=True)
class Task:
    id: uuid.UUID
    title: str
    description: str
    priority: int
    status: TaskStatus
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
    stage: Stage = Stage.INTAKE
    wait_reason: WaitReason = WaitReason.NONE
    lifecycle_version: int = 1
    requirement_version: int = 1
    project_name: str | None = None
    labels: tuple[str, ...] = ()
    estimate: float | None = None
    due_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        title: str,
        description: str = "",
        priority: int = 3,
        external_key: str | None = None,
        repository_id: uuid.UUID | None = None,
        project_name: str | None = None,
        labels: tuple[str, ...] = (),
        estimate: float | None = None,
        due_at: datetime | None = None,
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
            status=TaskStatus.NEW,
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
            project_name=project_name.strip() if project_name else None,
            labels=tuple(dict.fromkeys(label.strip() for label in labels if label.strip())),
            estimate=estimate,
            due_at=due_at,
        )
