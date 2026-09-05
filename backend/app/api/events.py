import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.db.models import TaskEvent
from app.db.session import SessionLocal

router = APIRouter(tags=["events"])


async def latest_event_id() -> int:
    async with SessionLocal() as session:
        return int(await session.scalar(select(func.max(TaskEvent.id))) or 0)


async def events_after(event_id: int) -> list[TaskEvent]:
    async with SessionLocal() as session:
        return list(
            (
                await session.scalars(
                    select(TaskEvent)
                    .where(TaskEvent.id > event_id)
                    .order_by(TaskEvent.id)
                    .limit(100)
                )
            ).all()
        )


async def sse_messages(
    request: Request, heartbeat_seconds: float = 15, poll_seconds: float = 1
) -> AsyncGenerator[str, None]:
    last_event_header = getattr(request, "headers", {}).get("last-event-id")
    try:
        cursor = (
            int(last_event_header) if last_event_header else max(0, await latest_event_id() - 100)
        )
    except ValueError:
        cursor = max(0, await latest_event_id() - 100)
    loop = asyncio.get_running_loop()
    last_message = loop.time()
    while not await request.is_disconnected():
        events = await events_after(cursor)
        if events:
            for item in events:
                cursor = item.id
                data = json.dumps(
                    {
                        "type": "task.event",
                        "event_id": item.id,
                        "task_id": str(item.task_id),
                        "event_type": item.event_type,
                    }
                )
                yield f"id: {item.id}\nevent: update\ndata: {data}\n\n"
                last_message = loop.time()
            continue
        elapsed = loop.time() - last_message
        if elapsed >= heartbeat_seconds:
            yield ": keepalive\n\n"
            last_message = loop.time()
        await asyncio.sleep(min(poll_seconds, heartbeat_seconds))


@router.get("/events/stream")
async def stream_events(request: Request) -> StreamingResponse:
    return StreamingResponse(
        sse_messages(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
