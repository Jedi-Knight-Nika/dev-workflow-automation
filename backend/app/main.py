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

from app.bootstrap.observability import observe_request
from app.bootstrap.scheduler import create_scheduler
from app.interfaces.http.routes.analytics import router as analytics_router
from app.interfaces.http.routes.control_plane import router as control_plane_router
from app.interfaces.http.routes.dashboard import router as dashboard_router
from app.interfaces.http.routes.events import router as events_router
from app.interfaces.http.routes.health import router as health_router
from app.interfaces.http.routes.metrics import router as metrics_router
from app.interfaces.http.routes.observability import router as observability_router
from app.interfaces.http.routes.settings import router as settings_router
from app.interfaces.http.routes.tasks import router as tasks_router
from app.interfaces.http.routes.teams import router as teams_router
from app.interfaces.http.routes.v2 import router as v2_router
from app.interfaces.http.routes.webhooks import router as webhooks_router
from app.platform.configuration.settings import get_settings
from app.platform.integrations.http import integration_http_pool
from app.platform.persistence import (
    registry as _registry,  # noqa: F401 -- register cross-context foreign keys
)
from app.platform.telemetry.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    scheduler = create_scheduler(settings) if settings.scheduler_enabled else None
    try:
        if scheduler is not None:
            await scheduler.start()
        yield
    finally:
        try:
            if scheduler is not None:
                await scheduler.stop()
        finally:
            await integration_http_pool.aclose()


app = FastAPI(title=settings.app_name, version="2.2.0", lifespan=lifespan)
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
app.include_router(settings_router, prefix="/api/v1")
app.include_router(control_plane_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(webhooks_router)
app.include_router(v2_router, prefix="/api/v1")
app.include_router(v2_router, prefix="/api", include_in_schema=False)
app.include_router(observability_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(metrics_router)


@app.middleware("http")
async def request_log(request: Request, call_next: RequestResponseEndpoint) -> Response:
    request_id = request.headers.get("x-request-id") or uuid4().hex
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        observe_request(request.url.path, request.method, 500, perf_counter() - started)
        log.exception(
            "http_request_failed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            duration_ms=round((perf_counter() - started) * 1000),
        )
        raise
    response.headers["x-request-id"] = request_id
    observe_request(
        request.url.path, request.method, response.status_code, perf_counter() - started
    )
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
