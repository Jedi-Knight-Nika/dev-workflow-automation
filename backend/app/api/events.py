import asyncio
from collections.abc import AsyncGenerator
from contextlib import suppress

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.events import broker

router = APIRouter(tags=["events"])


async def sse_messages(
    request: Request, heartbeat_seconds: float = 15
) -> AsyncGenerator[str, None]:
    subscription = broker.subscribe()
    pending: asyncio.Future[str] = asyncio.ensure_future(anext(subscription))
    try:
        while not await request.is_disconnected():
            done, _ = await asyncio.wait({pending}, timeout=heartbeat_seconds)
            if not done:
                yield ": keepalive\n\n"
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            yield f"event: update\ndata: {event}\n\n"
            pending = asyncio.ensure_future(anext(subscription))
    finally:
        pending.cancel()
        with suppress(asyncio.CancelledError):
            await pending
        await subscription.aclose()


@router.get("/events/stream")
async def stream_events(request: Request) -> StreamingResponse:

    return StreamingResponse(
        sse_messages(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
