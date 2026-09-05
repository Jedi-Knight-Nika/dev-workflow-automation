import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, ReviewFinding


def reviewer_fingerprint(job: Job) -> str:
    data = job.payload.get("data", {})
    value = data.get("workspace_fingerprint") if isinstance(data, dict) else None
    return str(value or "unknown")


def finding_fingerprint(item: dict[str, Any]) -> str:
    identity = {
        "severity": str(item.get("severity", "MEDIUM")).strip().upper(),
        "path": str(item.get("path") or "").strip(),
        "line": item.get("line") if isinstance(item.get("line"), int) else None,
        "message": " ".join(str(item.get("message") or "").lower().split()),
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def persist_review_result(session: AsyncSession, job: Job, result: dict[str, Any]) -> int:
    fingerprint = reviewer_fingerprint(job)
    existing = list(
        (
            await session.scalars(
                select(ReviewFinding).where(
                    ReviewFinding.task_id == job.task_id, ReviewFinding.status == "OPEN"
                )
            )
        ).all()
    )
    outcome = result.get("result")
    now = datetime.now(UTC)
    for finding in existing:
        if outcome == "PASS":
            finding.status = "RESOLVED"
            finding.resolved_at = now
        elif finding.workspace_fingerprint != fingerprint:
            finding.status = "STALE"
            finding.resolved_at = now
    data = result.get("data", {})
    findings = data.get("findings", []) if isinstance(data, dict) else []
    if outcome not in {"FAIL_ACTIONABLE", "FAIL_ARCHITECTURAL"} or not isinstance(findings, list):
        return 0
    highest_occurrence = 0
    for item in findings:
        if not isinstance(item, dict) or not item.get("message"):
            continue
        item_fingerprint = finding_fingerprint(item)
        previous_count = await session.scalar(
            select(func.max(ReviewFinding.occurrence_count)).where(
                ReviewFinding.task_id == job.task_id,
                ReviewFinding.finding_fingerprint == item_fingerprint,
            )
        )
        occurrence_count = (previous_count or 0) + 1
        highest_occurrence = max(highest_occurrence, occurrence_count)
        session.add(
            ReviewFinding(
                task_id=job.task_id,
                reviewer_job_id=job.id,
                workspace_fingerprint=fingerprint,
                finding_fingerprint=item_fingerprint,
                occurrence_count=occurrence_count,
                severity=str(item.get("severity", "MEDIUM"))[:20],
                file_path=str(item["path"]) if item.get("path") else None,
                line=item.get("line") if isinstance(item.get("line"), int) else None,
                message=str(item["message"]),
                last_seen_at=now,
            )
        )
    return highest_occurrence
