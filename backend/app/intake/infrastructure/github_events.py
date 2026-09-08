from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.infrastructure.task_models import Task, TaskRepositoryScope
from app.intake.infrastructure.webhook_models import WebhookDelivery
from app.platform.integrations.retry import DeliveryRetryPolicy
from app.platform.scheduling.states import JobState
from app.repositories.infrastructure.models import Repository

SUCCESSFUL_CHECKS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
FAILED_CHECKS = {
    "FAILURE",
    "FAILED",
    "ERROR",
    "CANCELLED",
    "TIMED_OUT",
    "ACTION_REQUIRED",
    "STALE",
}
BLOCKING_REVIEWS = {"CHANGES_REQUESTED"}
ACTIVE_JOB_STATES = {JobState.QUEUED, JobState.CLAIMED, JobState.RUNNING, JobState.RETRY_WAIT}
AUTHORIZED_MERGE_PERMISSIONS = {"admin", "maintain", "write"}
MERGE_APPROVAL_COMMENTS = {
    "/merge",
    "approve and merge",
    "approved",
    "looks good to me",
    "lgtm",
    "merge",
    "merge it",
    "go merge",
    "go ahead and merge",
    "please merge",
    "please merge it",
    "lgtm, merge it",
    "ready to merge",
}
MAX_DIAGNOSTIC_CHARS = 12_000
MAX_ANNOTATIONS = 20


def pull_request_number(payload: dict[str, Any]) -> int | None:
    value = (
        (payload.get("pull_request") or {}).get("number")
        or payload.get("number")
        or (payload.get("issue") or {}).get("number")
    )
    return value if isinstance(value, int) else None


def validation_from_event(
    event_type: str, payload: dict[str, Any]
) -> tuple[str, str, str, str, str | None] | None:
    if event_type == "check_run":
        item = payload.get("check_run", {})
        status = item.get("conclusion") or item.get("status") or "pending"
        return (
            "CHECK",
            item.get("name", "check"),
            str(status).upper(),
            item.get("head_sha", ""),
            item.get("html_url"),
        )
    if event_type == "check_suite":
        item = payload.get("check_suite", {})
        status = item.get("conclusion") or item.get("status") or "pending"
        return (
            "CHECK_SUITE",
            item.get("app", {}).get("name", "check suite"),
            str(status).upper(),
            item.get("head_sha", ""),
            item.get("url"),
        )
    if event_type == "status":
        return (
            "STATUS",
            payload.get("context", "status"),
            str(payload.get("state", "pending")).upper(),
            payload.get("sha", ""),
            payload.get("target_url"),
        )
    if event_type == "pull_request_review" and payload.get("action") == "submitted":
        review = payload.get("review", {})
        revision = review.get("commit_id") or payload.get("pull_request", {}).get("head", {}).get(
            "sha", ""
        )
        return (
            "REVIEW",
            review.get("user", {}).get("login", "review"),
            str(review.get("state", "commented")).upper(),
            revision,
            review.get("html_url"),
        )
    if event_type == "pull_request_review_comment" and payload.get("action") in {
        "created",
        "edited",
    }:
        comment = payload.get("comment", {})
        return (
            "REVIEW_COMMENT",
            comment.get("user", {}).get("login", "review comment"),
            "ACTION_REQUIRED",
            comment.get("commit_id")
            or payload.get("pull_request", {}).get("head", {}).get("sha", ""),
            comment.get("html_url"),
        )
    return None


async def process_github_event(
    session: AsyncSession, event_type: str, payload: dict[str, Any]
) -> None:
    repository_payload = payload.get("repository") or {}
    external_id = repository_payload.get("id")
    if external_id is None:
        return
    repository = await session.scalar(
        select(Repository).where(
            Repository.provider == "github", Repository.external_repo_id == str(external_id)
        )
    )
    if repository is None:
        return
    if event_type == "issues":
        from app.intake.infrastructure.github_issues import issue_event

        await issue_event(session, repository, payload)
        return
    number = pull_request_number(payload)
    if number is None and event_type in {"check_run", "check_suite"}:
        pull_requests = payload.get(event_type, {}).get("pull_requests", [])
        if pull_requests:
            number = pull_requests[0].get("number")
    evidence = validation_from_event(event_type, payload)
    scope = None
    if number is not None:
        scope = await session.scalar(
            select(TaskRepositoryScope).where(
                TaskRepositoryScope.repository_id == repository.id,
                TaskRepositoryScope.pull_request_number == int(number),
            )
        )
    elif evidence and evidence[3]:
        scope = await session.scalar(
            select(TaskRepositoryScope).where(
                TaskRepositoryScope.repository_id == repository.id,
                TaskRepositoryScope.current_revision == evidence[3],
            )
        )
    if number is not None:
        task = await session.scalar(
            select(Task).where(
                Task.repository_id == repository.id, Task.pull_request_number == int(number)
            )
        )
    elif evidence and evidence[3]:
        task = await session.scalar(
            select(Task).where(
                Task.repository_id == repository.id, Task.current_revision == evidence[3]
            )
        )
    else:
        return
    if task is None and scope is not None:
        task = await session.get(Task, scope.task_id)
    if task is None:
        return
    from app.intake.infrastructure.v2_events import github_event

    await github_event(session, task, repository, event_type, payload)


async def process_next_github_delivery(session: AsyncSession, max_attempts: int = 5) -> bool:
    retry_policy = DeliveryRetryPolicy(max_attempts)
    delivery = await session.scalar(
        select(WebhookDelivery)
        .where(WebhookDelivery.provider == "github", WebhookDelivery.status == "RECEIVED")
        .order_by(WebhookDelivery.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if delivery is None:
        return False
    delivery_id = delivery.id
    try:
        delivery.attempts += 1
        await process_github_event(session, delivery.event_type, delivery.payload)
        delivery.status = "PROCESSED"
        delivery.last_error = None
        delivery.processed_at = datetime.now(UTC)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        failed = await session.get(WebhookDelivery, delivery_id, with_for_update=True)
        if failed is None:
            raise
        failed.attempts += 1
        failed.last_error = retry_policy.error_message(exc)
        if retry_policy.exhausted(failed.attempts):
            failed.status = "FAILED"
            failed.processed_at = datetime.now(UTC)
        await session.commit()
    return True
