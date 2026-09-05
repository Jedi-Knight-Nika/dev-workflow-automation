from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.application.ports.job_enqueueing import EnqueuedJob


@dataclass(frozen=True, slots=True)
class ActivityView:
    active_job: EnqueuedJob | None
    queued_jobs: list[EnqueuedJob]


@dataclass(frozen=True, slots=True)
class WebhookHealthView:
    provider: str
    pending: int
    failed: int
    last_delivery_at: datetime | None
    last_processed_at: datetime | None
    last_error: str | None


class OperationsQueries(Protocol):
    async def activity(self) -> ActivityView: ...
    async def webhook_health(self) -> list[WebhookHealthView]: ...
