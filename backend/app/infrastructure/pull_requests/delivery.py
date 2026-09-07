"""Deterministic, scope-aware delivery shared by validation and review gates."""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Repository, Task, TaskRepositoryScope, TaskState
from app.infrastructure.persistence.job_operations import record_event
from app.infrastructure.pull_requests.operations import publish_pull_request


async def publish_task_repositories(session: AsyncSession, task_id: uuid.UUID) -> None:
    try:
        task = await session.get(Task, task_id, with_for_update=True)
        if task is None or task.state != TaskState.WAITING_GITHUB or task.manual_takeover:
            return
        rows = (
            await session.execute(
                select(TaskRepositoryScope, Repository)
                .join(Repository, Repository.id == TaskRepositoryScope.repository_id)
                .where(
                    TaskRepositoryScope.task_id == task.id, TaskRepositoryScope.changed.is_(True)
                )
                .order_by(TaskRepositoryScope.is_primary.desc())
            )
        ).all()
        if not rows and task.repository_id is not None:
            repository = await session.get(Repository, task.repository_id)
            if repository is not None:
                await publish_pull_request(session, task, repository)
            return
        for scope, repository in rows:
            if scope.merged_at is not None:
                continue
            if not repository.enabled:
                raise RuntimeError("Reviewed task repository is unavailable")
            await publish_pull_request(session, task, repository, scope)
    except Exception:  # noqa: BLE001 - retain task and provide a safe operator error
        structlog.get_logger().exception(
            "automatic_pull_request_publish_failed", task_id=str(task_id)
        )
        await session.rollback()
        task = await session.get(Task, task_id, with_for_update=True)
        if task is None:
            return
        task.state = TaskState.NEEDS_HUMAN
        await record_event(
            session,
            task.id,
            "AUTOMATIC_PR_PUBLISH_FAILED",
            {
                "error": "Could not publish the task's pull requests. Check GitHub connection and delivery logs."
            },
        )
        await session.commit()
