from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.operations_queries import ActivityView, WebhookHealthView
from app.db.models import Job, JobState, WebhookDelivery
from app.infrastructure.persistence.job_enqueueing import job_to_view


class SqlAlchemyOperationsQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def activity(self) -> ActivityView:
        active = await self._session.scalar(
            select(Job)
            .where(Job.state.in_([JobState.CLAIMED, JobState.RUNNING]))
            .order_by(Job.started_at, Job.created_at)
            .limit(1)
        )
        queued = (
            await self._session.scalars(
                select(Job)
                .where(Job.state.in_([JobState.QUEUED, JobState.RETRY_WAIT]))
                .order_by(Job.priority, Job.created_at)
                .limit(20)
            )
        ).all()
        return ActivityView(
            job_to_view(active) if active is not None else None,
            [job_to_view(job) for job in queued],
        )

    async def webhook_health(self) -> list[WebhookHealthView]:
        health: list[WebhookHealthView] = []
        for provider in ("github", "linear", "trello"):
            pending = await self._session.scalar(
                select(func.count(WebhookDelivery.id)).where(
                    WebhookDelivery.provider == provider,
                    WebhookDelivery.status == "RECEIVED",
                )
            )
            failed = await self._session.scalar(
                select(func.count(WebhookDelivery.id)).where(
                    WebhookDelivery.provider == provider,
                    WebhookDelivery.status == "FAILED",
                )
            )
            latest = await self._session.scalar(
                select(WebhookDelivery)
                .where(WebhookDelivery.provider == provider)
                .order_by(WebhookDelivery.created_at.desc())
                .limit(1)
            )
            latest_error = await self._session.scalar(
                select(WebhookDelivery)
                .where(
                    WebhookDelivery.provider == provider,
                    WebhookDelivery.last_error.is_not(None),
                )
                .order_by(WebhookDelivery.created_at.desc())
                .limit(1)
            )
            health.append(
                WebhookHealthView(
                    provider,
                    int(pending or 0),
                    int(failed or 0),
                    latest.created_at if latest else None,
                    latest.processed_at if latest else None,
                    latest_error.last_error if latest_error else None,
                )
            )
        return health
