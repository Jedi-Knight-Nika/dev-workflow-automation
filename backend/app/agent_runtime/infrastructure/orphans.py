"""Stop expired, provably owned runners; retain stopped-container evidence."""

import json
import re
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import AIRun, DeveloperSession, Job, JobState, Task, TaskEvent

UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
NAME = re.compile(rf"/(?:developer|validation|prepare|publish)-({UUID_PATTERN})-({UUID_PATTERN})")


async def sweep(client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]) -> None:
    response = await client.get(
        "/containers/json",
        params={
            "filters": json.dumps({"label": ["managed_by=scheduler-v2"], "status": ["running"]})
        },
    )
    response.raise_for_status()
    containers = response.json()
    if not isinstance(containers, list) or len(containers) > 500:
        raise ValueError("Orphan inspection exceeds its safety bound")
    for container in containers:
        names = container.get("Names") or []
        match = NAME.fullmatch(names[0]) if len(names) == 1 else None
        if match is None or container.get("Labels", {}).get("managed_by") != "scheduler-v2":
            continue
        job_id, token = UUID(match[1]), UUID(match[2])
        async with sessions.begin() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None or container.get("Labels", {}).get("task_id") != str(job.task_id):
                continue  # May belong to another installation; never guess ownership.
            task = await session.get(Task, job.task_id)
            if task is None or task.execution_version != 2:
                continue
            if (
                job.lease_token == token
                and job.state in {JobState.CLAIMED, JobState.RUNNING}
                and job.lease_expires_at
                and job.lease_expires_at > datetime.now(UTC)
                and task.status in {"NEW", "ACTIVE"}
                and not task.manual_takeover
            ):
                continue
            result = await client.post(f"/containers/{container['Id']}/stop", params={"t": 5})
            if result.status_code not in {204, 304, 404}:
                result.raise_for_status()
            # Revoked jobs are no longer eligible for lease-expiry recovery.
            # Close their reservations only after stopping the owned container;
            # absent receipts remain unknown, never zero or the reserved amount.
            runs = await session.scalars(
                select(AIRun)
                .where(AIRun.job_id == job.id, AIRun.status == "RUNNING")
                .with_for_update()
            )
            for run in runs:
                run.status, run.failure_code, run.finished_at = (
                    "INTERRUPTED",
                    "ORPHAN_STOPPED",
                    datetime.now(UTC),
                )
                if run.session_id:
                    native = await session.get(DeveloperSession, run.session_id)
                    if native:
                        native.state = "BLOCKED"
            session.add(
                TaskEvent(
                    task_id=task.id,
                    source="scheduler-v2",
                    event_type="V2_ORPHAN_STOPPED",
                    payload={
                        "job_id": str(job.id),
                        "container_id": container["Id"],
                        "evidence_retained": True,
                    },
                )
            )


async def reap_orphans(sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    async with httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(uds=str(settings.docker_socket)),
        base_url="http://docker",
        timeout=10,
    ) as client:
        await sweep(client, sessions)
