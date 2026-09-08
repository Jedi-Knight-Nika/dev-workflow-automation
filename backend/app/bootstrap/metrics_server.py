"""Controller-only private metrics listener; no scheduler or API privileges."""

import uvicorn
from fastapi import FastAPI

from app.interfaces.http.routes.metrics import router


async def serve_metrics() -> None:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router)
    server = uvicorn.Server(
        uvicorn.Config(app, host="0.0.0.0", port=8001, log_level="warning", lifespan="off")
    )
    # Do not install signal handlers over the scheduler's shutdown handler.
    await server._serve()  # the surrounding worker owns signals and cancellation
