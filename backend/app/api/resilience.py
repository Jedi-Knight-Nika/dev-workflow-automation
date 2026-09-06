import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.ports.resilience_queries import ResilienceQueries
from app.bootstrap.dependencies import get_resilience_queries

router = APIRouter(tags=["resilience"])


@router.get("/resilience/health")
async def health(
    queries: Annotated[ResilienceQueries, Depends(get_resilience_queries)],
) -> list[dict[str, object]]:
    return await queries.health()


@router.get("/jobs/{job_id}/failure-history")
async def failure_history(
    job_id: uuid.UUID,
    queries: Annotated[ResilienceQueries, Depends(get_resilience_queries)],
) -> list[dict[str, object]]:
    return await queries.failure_history(job_id)


@router.get("/tasks/{task_id}/blocking-reason")
async def blocking_reason(
    task_id: uuid.UUID,
    queries: Annotated[ResilienceQueries, Depends(get_resilience_queries)],
) -> dict[str, object] | None:
    return await queries.blocking_reason(task_id)
