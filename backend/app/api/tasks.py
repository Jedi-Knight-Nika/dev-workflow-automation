import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, JobRole, JobState, Task, TaskEvent, TaskState
from app.db.session import get_session
from app.schemas import EventRead, JobCreate, JobRead, TaskCreate, TaskRead
from app.services.events import broker
from app.services.orchestrator import enqueue_job, record_event

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    limit: int = Query(default=100, ge=1, le=500), session: AsyncSession = Depends(get_session)
) -> list[Task]:
    return list(
        (await session.scalars(select(Task).order_by(Task.created_at.desc()).limit(limit))).all()
    )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskCreate, session: AsyncSession = Depends(get_session)) -> Task:
    task = Task(
        external_key=body.external_key,
        title=body.title,
        description=body.description,
        priority=body.priority,
    )
    session.add(task)
    await session.flush()
    await record_event(session, task.id, "TASK_CREATED", {"title": task.title}, source="api")
    if body.enqueue_planning:
        await enqueue_job(session, task, JobRole.THINKER, "CREATE_PLAN")
    await session.commit()
    await session.refresh(task)
    await broker.publish(json.dumps({"type": "task.created", "task_id": str(task.id)}))
    return task


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/jobs", response_model=list[JobRead])
async def list_task_jobs(
    task_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[Job]:
    return list(
        (
            await session.scalars(
                select(Job).where(Job.task_id == task_id).order_by(Job.created_at)
            )
        ).all()
    )


@router.post("/{task_id}/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    task_id: uuid.UUID, body: JobCreate, session: AsyncSession = Depends(get_session)
) -> Job:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.state in (TaskState.CANCELLED, TaskState.PAUSED):
        raise HTTPException(
            status_code=409, detail=f"Cannot enqueue work for {task.state.value} task"
        )
    job = await enqueue_job(session, task, body.role, body.action, body.priority, body.payload)
    await session.commit()
    await session.refresh(job)
    await broker.publish(json.dumps({"type": "job.created", "job_id": str(job.id)}))
    return job


@router.get("/{task_id}/events", response_model=list[EventRead])
async def list_task_events(
    task_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[TaskEvent]:
    return list(
        (
            await session.scalars(
                select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id)
            )
        ).all()
    )


@router.post("/{task_id}/pause", response_model=TaskRead)
async def pause_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.state = TaskState.PAUSED
    await record_event(session, task.id, "TASK_PAUSED", {}, source="user")
    await session.commit()
    return task


@router.post("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.state = TaskState.CANCELLED
    queued = (
        await session.scalars(
            select(Job).where(Job.task_id == task.id, Job.state == JobState.QUEUED)
        )
    ).all()
    for job in queued:
        job.state = JobState.CANCELLED
    await record_event(
        session, task.id, "TASK_CANCELLED", {"cancelled_jobs": len(queued)}, source="user"
    )
    await session.commit()
    return task
