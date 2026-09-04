import asyncio
import sys
import uuid

from sqlalchemy import select

from app.db.models import Job
from app.db.session import SessionLocal
from app.schemas import WorkerResult


async def run(job_id: uuid.UUID) -> WorkerResult:
    async with SessionLocal() as session:
        job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()
        # This deterministic worker proves the protocol and lifecycle. Provider-backed
        # implementations replace this handler role-by-role in later phases.
        return WorkerResult(
            job_id=job.id,
            task_id=job.task_id,
            role=job.role,
            result=f"{job.role.value}_PLACEHOLDER_COMPLETED",
            summary=f"Validated worker lifecycle for action {job.action}",
            data={"action": job.action, "payload_keys": sorted(job.payload)},
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.worker JOB_ID")
    output = asyncio.run(run(uuid.UUID(sys.argv[1])))
    print(output.model_dump_json())
