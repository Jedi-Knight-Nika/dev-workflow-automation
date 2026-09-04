import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.events import broker

router = APIRouter(tags=["events"])


@router.get("/events/stream")
async def stream_events(request: Request) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        iterator = broker.subscribe().__aiter__()
        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(iterator.__anext__(), timeout=15)
                yield f"event: update\ndata: {event}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
