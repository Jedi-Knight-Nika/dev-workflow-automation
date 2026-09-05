import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.api.control_plane import router as control_plane_router
from app.api.dashboard import router as dashboard_router
from app.api.events import router as events_router
from app.api.execution_policy import router as execution_policy_router
from app.api.health import router as health_router
from app.api.notifications import router as notifications_router
from app.api.notifications import webhook_router as telegram_webhook_router
from app.api.roles import router as roles_router
from app.api.tasks import router as tasks_router
from app.api.teams import router as teams_router
from app.api.terminals import router as terminals_router
from app.api.webhooks import router as webhooks_router
from app.bootstrap.scheduler import create_scheduler
from app.config import get_settings
from app.db.session import SessionLocal
from app.infrastructure.telegram import TelegramService
from app.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
log = structlog.get_logger()
scheduler = create_scheduler(settings)


async def notification_delivery_loop() -> None:
    while True:
        try:
            async with SessionLocal() as session:
                await TelegramService(session, settings).deliver_pending()
        except Exception:
            log.exception("notification_delivery_failed")
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    notification_task = asyncio.create_task(notification_delivery_loop())
    if settings.scheduler_enabled:
        await scheduler.start()
    yield
    notification_task.cancel()
    await asyncio.gather(notification_task, return_exceptions=True)
    if settings.scheduler_enabled:
        await scheduler.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(teams_router, prefix="/api/v1")
app.include_router(roles_router, prefix="/api/v1")
app.include_router(terminals_router, prefix="/api/v1")
app.include_router(control_plane_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(execution_policy_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(webhooks_router)
app.include_router(telegram_webhook_router)


@app.middleware("http")
async def request_log(request: Request, call_next: RequestResponseEndpoint) -> Response:
    request_id = request.headers.get("x-request-id") or uuid4().hex
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception(
            "http_request_failed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            duration_ms=round((perf_counter() - started) * 1000),
        )
        raise
    response.headers["x-request-id"] = request_id
    log.info(
        "http_request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round((perf_counter() - started) * 1000),
    )
    return response


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
