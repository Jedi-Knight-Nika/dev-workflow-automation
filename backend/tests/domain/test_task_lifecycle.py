import types
import uuid
from datetime import UTC, datetime
from typing import Self

import pytest

from app.application.ports.task_lifecycle import TaskLifecycleContext
from app.application.tasks import ChangeTaskLifecycle, TaskNotFound
from app.domain.tasks import (
    InvalidTaskTransition,
    LifecycleAction,
    LifecycleDirective,
    Task,
    TaskState,
)


class FakeLifecycleUnitOfWork:
    def __init__(self, context: TaskLifecycleContext | None) -> None:
        self.context = context
        self.directive: LifecycleDirective | None = None
        self.refreshed = False
        self.committed = False
        self.synchronized = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        return None

    async def load(self, _task_id: uuid.UUID) -> TaskLifecycleContext | None:
        return self.context

    async def refresh_workspace(self, _task_id: uuid.UUID) -> tuple[str, str]:
        self.refreshed = True
        return "revision", "fingerprint"

    async def apply(
        self,
        context: TaskLifecycleContext,
        directive: LifecycleDirective,
        *,
        revision: str | None,
        workspace_fingerprint: str | None,
    ) -> Task:
        self.directive = directive
        now = datetime.now(UTC)
        return Task(
            context.task_id,
            "Task",
            "",
            3,
            directive.state,
            None,
            None,
            revision,
            None,
            "/tmp/work" if context.has_workspace else None,
            1 if context.has_pull_request else None,
            None,
            directive.manual_takeover,
            now,
            now,
        )

    async def commit(self) -> None:
        self.committed = True

    async def synchronize_tracker(self, _task_id: uuid.UUID) -> None:
        self.synchronized = True


def context(
    *,
    state: TaskState = TaskState.NEW,
    takeover: bool = False,
    pull_request: bool = False,
    workspace: bool = False,
) -> TaskLifecycleContext:
    return TaskLifecycleContext(uuid.uuid4(), state, takeover, pull_request, workspace)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_state", "takeover", "cancel_jobs"),
    [
        (LifecycleAction.PAUSE, TaskState.PAUSED, False, False),
        (LifecycleAction.CANCEL, TaskState.CANCELLED, False, True),
        (LifecycleAction.TAKEOVER, TaskState.PAUSED, True, True),
    ],
)
async def test_task_lifecycle_applies_domain_transition(
    action: LifecycleAction, expected_state: TaskState, takeover: bool, cancel_jobs: bool
) -> None:
    unit = FakeLifecycleUnitOfWork(context())
    result = await ChangeTaskLifecycle(lambda: unit).execute(unit.context.task_id, action)  # type: ignore[union-attr,arg-type]
    assert result.state == expected_state
    assert unit.directive == LifecycleDirective(expected_state, takeover, cancel_jobs)
    assert unit.committed and unit.synchronized


@pytest.mark.asyncio
async def test_attention_task_can_be_reopened_to_backlog() -> None:
    unit = FakeLifecycleUnitOfWork(context(state=TaskState.NEEDS_HUMAN))

    result = await ChangeTaskLifecycle(lambda: unit).execute(  # type: ignore[arg-type,union-attr]
        unit.context.task_id, LifecycleAction.REOPEN
    )

    assert result.state == TaskState.NEW
    assert unit.directive == LifecycleDirective(TaskState.NEW, False, True)
    assert unit.committed and unit.synchronized


@pytest.mark.asyncio
async def test_merged_task_cannot_be_reopened() -> None:
    unit = FakeLifecycleUnitOfWork(context(state=TaskState.MERGED))

    with pytest.raises(InvalidTaskTransition, match="Merged tasks"):
        await ChangeTaskLifecycle(lambda: unit).execute(  # type: ignore[arg-type,union-attr]
            unit.context.task_id, LifecycleAction.REOPEN
        )


@pytest.mark.asyncio
async def test_resume_refreshes_workspace_and_returns_to_github() -> None:
    unit = FakeLifecycleUnitOfWork(context(takeover=True, pull_request=True, workspace=True))
    result = await ChangeTaskLifecycle(lambda: unit).execute(
        unit.context.task_id, LifecycleAction.RESUME
    )  # type: ignore[union-attr,arg-type]
    assert result.state == TaskState.WAITING_GITHUB
    assert result.current_revision == "revision"
    assert unit.refreshed and unit.committed


@pytest.mark.asyncio
async def test_takeover_rejects_terminal_task() -> None:
    unit = FakeLifecycleUnitOfWork(context(state=TaskState.MERGED))
    with pytest.raises(InvalidTaskTransition, match="Cannot take over"):
        await ChangeTaskLifecycle(lambda: unit).execute(
            unit.context.task_id, LifecycleAction.TAKEOVER
        )  # type: ignore[union-attr,arg-type]
    assert not unit.committed


@pytest.mark.asyncio
async def test_only_terminal_tasks_can_be_archived() -> None:
    active = FakeLifecycleUnitOfWork(context(state=TaskState.IMPLEMENTING))
    with pytest.raises(InvalidTaskTransition, match="Only terminal"):
        await ChangeTaskLifecycle(lambda: active).execute(  # type: ignore[arg-type,union-attr]
            active.context.task_id, LifecycleAction.ARCHIVE
        )

    terminal = FakeLifecycleUnitOfWork(context(state=TaskState.MERGED))
    await ChangeTaskLifecycle(lambda: terminal).execute(  # type: ignore[arg-type,union-attr]
        terminal.context.task_id, LifecycleAction.ARCHIVE
    )
    assert terminal.directive == LifecycleDirective(TaskState.MERGED, False, True, True)
    assert terminal.committed


@pytest.mark.asyncio
async def test_missing_task_is_reported() -> None:
    unit = FakeLifecycleUnitOfWork(None)
    with pytest.raises(TaskNotFound):
        await ChangeTaskLifecycle(lambda: unit).execute(uuid.uuid4(), LifecycleAction.PAUSE)  # type: ignore[arg-type]
