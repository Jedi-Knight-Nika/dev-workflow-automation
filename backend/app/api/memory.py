import uuid
from collections.abc import Awaitable

from fastapi import APIRouter, Depends, HTTPException

from app.application.ports.task_memory import TaskMemoryQueries
from app.application.query_task_memory import QueryTaskMemory
from app.bootstrap.dependencies import get_task_memory_queries

router = APIRouter(tags=["task-memory"])


async def resolve[T](call: Awaitable[T]) -> T:
    try:
        return await call
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/memory")
async def memory(
    task_id: uuid.UUID, queries: TaskMemoryQueries = Depends(get_task_memory_queries)
) -> dict[str, object]:
    return await resolve(QueryTaskMemory(queries).memory(task_id))


@router.get("/tasks/{task_id}/checkpoints")
async def checkpoints(
    task_id: uuid.UUID, queries: TaskMemoryQueries = Depends(get_task_memory_queries)
) -> list[dict[str, object]]:
    return await resolve(QueryTaskMemory(queries).checkpoints(task_id))


@router.get("/tasks/{task_id}/context-history")
async def contexts(
    task_id: uuid.UUID, queries: TaskMemoryQueries = Depends(get_task_memory_queries)
) -> list[dict[str, object]]:
    return await resolve(QueryTaskMemory(queries).contexts(task_id))


@router.get("/jobs/{job_id}/context-metadata")
async def job_context(
    job_id: uuid.UUID, queries: TaskMemoryQueries = Depends(get_task_memory_queries)
) -> dict[str, object]:
    return await resolve(QueryTaskMemory(queries).job_context(job_id))
