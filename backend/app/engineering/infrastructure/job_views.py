from app.engineering.application.ports.job_enqueueing import (
    EnqueuedJob,
)
from app.engineering.infrastructure.task_models import Job


def job_to_view(job: Job) -> EnqueuedJob:
    return EnqueuedJob(
        id=job.id,
        task_id=job.task_id,
        action=job.action,
        priority=job.priority,
        state=job.state.value,
        attempt=job.attempt,
        payload=job.payload,
        result=job.result,
        worker_id=job.worker_id,
        failure_reason=job.failure_reason,
        retry_not_before=job.retry_not_before,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
