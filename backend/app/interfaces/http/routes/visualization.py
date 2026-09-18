import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.activity.application.ports import (
    ActivityMonitor,
    ActivityQueries,
    ActivityScope,
    ActivityWindow,
)
from app.bootstrap.activity import get_activity_monitor, get_activity_queries
from app.bootstrap.streams import activity_signal
from app.interfaces.http.errors import service_errors
from app.platform.configuration.settings import get_settings
from app.platform.scheduling.stream_signal import wait_for_change

router = APIRouter(prefix="/visualization", tags=["visualization"])
ScopeKind = Literal["workspace", "project", "team", "task", "repository"]
MAX_SEQUENCE = 2**53 - 1  # JSON/browser integers must remain exact.


class ScopeInput(BaseModel):
    type: ScopeKind = "workspace"
    id: str | None = Field(default=None, max_length=255)


class PreflightInput(BaseModel):
    scope: ScopeInput = Field(default_factory=ScopeInput)
    start: datetime = Field(alias="from")
    end: datetime | None = Field(default=None, alias="to")
    detail: int = Field(default=2, ge=1, le=2)


class ViewerReport(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    draws: int = Field(default=0, ge=0, le=1000000)
    render_ms: float = Field(default=0, ge=0, le=3600000)
    init_ms: float | None = Field(default=None, ge=0, le=3600000)
    reconnects: int = Field(default=0, ge=0, le=10000)
    worker_crashes: int = Field(default=0, ge=0, le=100)
    graphics_failures: int = Field(default=0, ge=0, le=100)
    gource_failures: int = Field(default=0, ge=0, le=100)
    session_seconds: float = Field(default=0, ge=0, le=86400)


@router.post("/telemetry", status_code=204)
async def telemetry(
    body: ViewerReport, monitor: ActivityMonitor = Depends(get_activity_monitor)
) -> None:
    if not get_settings().activity_enabled:
        raise HTTPException(503, "Activity visualization is disabled")
    monitor.client_report(body.model_dump())


def make_window(
    kind: str, id: str | None, start: datetime, end: datetime | None, detail: int
) -> ActivityWindow:
    settings = get_settings()
    if not settings.activity_enabled:
        raise HTTPException(503, "Activity visualization is disabled")
    end = end or datetime.now(UTC)
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "Activity timestamps must include a timezone")
    if end <= start or end - start > timedelta(days=settings.activity_max_replay_days):
        raise HTTPException(422, "Choose a valid, bounded activity time range")
    return ActivityWindow(ActivityScope(kind, id), start, end, detail)


def read_window(
    scope_type: ScopeKind = "workspace",
    scope_id: str | None = Query(None, max_length=255),
    start: datetime | None = Query(None, alias="from"),
    end: datetime | None = Query(None, alias="to"),
    detail: int = Query(2, ge=1, le=2),
) -> ActivityWindow:
    return make_window(
        scope_type, scope_id, start or datetime.now(UTC) - timedelta(days=1), end, detail
    )


@router.get("/scopes")
async def scopes(queries: ActivityQueries = Depends(get_activity_queries)) -> dict[str, Any]:
    if not get_settings().activity_enabled:
        raise HTTPException(503, "Activity visualization is disabled")
    return await queries.choices()


@router.post("/preflight")
async def preflight(
    body: PreflightInput, queries: ActivityQueries = Depends(get_activity_queries)
) -> dict[str, Any]:
    window = make_window(body.scope.type, body.scope.id, body.start, body.end, body.detail)
    with service_errors(value_status=422):
        return await queries.preflight(window)


@router.get("/events")
async def events(
    window: ActivityWindow = Depends(read_window),
    after_sequence: int = Query(0, ge=0, le=MAX_SEQUENCE),
    through_sequence: int | None = Query(None, ge=0, le=MAX_SEQUENCE),
    limit: int = Query(250, ge=1, le=500),
    queries: ActivityQueries = Depends(get_activity_queries),
) -> dict[str, Any]:
    with service_errors(value_status=422):
        return await queries.events(window, after_sequence, through_sequence, limit)


@router.get("/baseline")
async def baseline(
    through_sequence: int = Query(ge=0, le=MAX_SEQUENCE),
    window: ActivityWindow = Depends(read_window),
    queries: ActivityQueries = Depends(get_activity_queries),
) -> dict[str, Any]:
    with service_errors(value_status=422):
        return await queries.baseline(window, through_sequence)


@router.get("/aggregate")
async def aggregate(
    through_sequence: int = Query(ge=0, le=MAX_SEQUENCE),
    window: ActivityWindow = Depends(read_window),
    queries: ActivityQueries = Depends(get_activity_queries),
) -> dict[str, Any]:
    with service_errors(value_status=422):
        return await queries.aggregate(window, through_sequence)


@router.get("/inspect/{sequence}")
async def inspect(
    sequence: int,
    through_sequence: int = Query(ge=0, le=MAX_SEQUENCE),
    window: ActivityWindow = Depends(read_window),
    queries: ActivityQueries = Depends(get_activity_queries),
) -> dict[str, Any]:
    if not 1 <= sequence <= MAX_SEQUENCE:
        raise HTTPException(422, "Invalid activity sequence")
    with service_errors(value_status=422):
        return await queries.inspect(window, sequence, through_sequence)


async def stream_messages(
    request: Request,
    queries: ActivityQueries,
    window: ActivityWindow,
    cursor: int,
    listener: asyncio.Event | None = None,
) -> AsyncIterator[str]:
    heartbeat = 0
    changed = True
    while not await request.is_disconnected():
        # Include late historical projections. A baseline-changing backfill
        # explicitly resets the viewer rather than silently losing old state.
        live = ActivityWindow(
            window.scope, datetime(1970, 1, 1, tzinfo=UTC), datetime.now(UTC), window.detail
        )
        try:
            page: dict[str, Any] = (
                await queries.events(live, cursor, None, 250)
                if changed
                else {"events": [], "next_sequence": cursor, "has_more": False}
            )
        except (LookupError, ValueError):
            yield "event: unavailable\ndata: {}\n\n"
            return
        for event in page["events"]:
            if event["occurred_at"] < window.start:
                yield 'event: reset\ndata: {"reason":"Historical activity changed"}\n\n'
                return
            data = json.dumps(jsonable_encoder(event), separators=(",", ":"))
            yield f"id: {event['sequence']}\nevent: activity\ndata: {data}\n\n"
        cursor = page["next_sequence"]
        yield f'id: {cursor}\nevent: cursor\ndata: {{"sequence":{cursor}}}\n\n'
        if page["has_more"]:
            continue
        if listener is not None or heartbeat % 10 == 0:
            status_window = ActivityWindow(
                window.scope, window.start, datetime.now(UTC), window.detail
            )
            status = json.dumps(
                jsonable_encoder(
                    {
                        **await queries.projection_status(),
                        "file_history": await queries.coverage(status_window),
                        "capacity": await queries.capacity(status_window, cursor),
                    }
                )
            )
            yield f"event: status\ndata: {status}\n\n"
        heartbeat += 1
        if listener is None:
            await asyncio.sleep(1)
        else:
            changed = await wait_for_change(listener, 10)


@router.get("/stream")
async def stream(
    request: Request,
    window: ActivityWindow = Depends(read_window),
    after_sequence: int = Query(0, ge=0, le=MAX_SEQUENCE),
    queries: ActivityQueries = Depends(get_activity_queries),
    monitor: ActivityMonitor = Depends(get_activity_monitor),
) -> StreamingResponse:
    try:
        await queries.preflight(window)  # Validate scope before sending response headers.
        resumed = int(request.headers.get("last-event-id", "0"))
        if not 0 <= resumed <= MAX_SEQUENCE:
            raise ValueError("Invalid activity cursor")
        cursor = max(after_sequence, resumed)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid activity scope or cursor") from exc

    async def monitored_stream() -> AsyncIterator[str]:
        monitor.stream_open(cursor > 0)
        try:
            async with activity_signal().subscribe() as listener:
                async for message in stream_messages(request, queries, window, cursor, listener):
                    yield message
        finally:
            monitor.stream_close()

    return StreamingResponse(
        monitored_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
