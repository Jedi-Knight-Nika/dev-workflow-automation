"""Associate deployment facts only with an explicitly recorded repository and SHA."""

from sqlalchemy import String, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.domain.events import Activity
from app.delivery.infrastructure.deployment_models import DeploymentObservation
from app.delivery.infrastructure.deployments import deployment_payload
from app.engineering.infrastructure.task_models import Task, TaskEvent, TaskRepositoryScope


async def deployment_activities(session: AsyncSession, limit: int, version: int) -> list[Activity]:
    from app.activity.infrastructure.models import ActivityEvent

    # UNION removes duplicate associations when a primary scope also belongs to
    # the task. No branch ancestry or time-proximity inference is used.
    revisions = (
        select(
            Task.id.label("task_id"),
            Task.repository_id.label("repository_id"),
            Task.current_revision.label("sha"),
        )
        .union(
            select(
                TaskRepositoryScope.task_id,
                TaskRepositoryScope.repository_id,
                TaskRepositoryScope.current_revision,
            ),
            select(
                TaskRepositoryScope.task_id,
                TaskRepositoryScope.repository_id,
                TaskRepositoryScope.merge_commit_sha,
            ),
            select(
                TaskEvent.task_id, Task.repository_id, TaskEvent.payload["merge_sha"].as_string()
            )
            .join(Task, Task.id == TaskEvent.task_id)
            .where(
                TaskEvent.event_type.in_(["ENGINEERING_MERGE_CONFIRMED", "GITHUB_MERGE_OBSERVED"])
            ),
        )
        .subquery()
    )
    identity = cast(DeploymentObservation.id, String) + ":" + cast(revisions.c.task_id, String)
    projected = (
        select(ActivityEvent.sequence)
        .where(
            ActivityEvent.source_type == "deployment",
            ActivityEvent.source_id == identity,
            ActivityEvent.projector_version >= version,
        )
        .exists()
    )
    rows = (
        await session.execute(
            select(DeploymentObservation, revisions.c.task_id, identity)
            .join(
                revisions,
                (revisions.c.repository_id == DeploymentObservation.repository_id)
                & (revisions.c.sha == DeploymentObservation.sha),
            )
            .join(Task, Task.id == revisions.c.task_id)
            .where(~projected, Task.created_at <= DeploymentObservation.occurred_at)
            .order_by(DeploymentObservation.id, revisions.c.task_id)
            .limit(limit)
        )
    ).all()
    return [
        Activity(
            "deployment",
            source_id,
            task_id,
            "DEPLOYMENT_STATUS_CHANGED",
            row.occurred_at,
            "integration",
            "GitHub",
            2,
            payload=deployment_payload(row),
        )
        for row, task_id, source_id in rows
    ]
