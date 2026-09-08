from secrets import compare_digest

from fastapi import APIRouter, Header, HTTPException, Response

from app.bootstrap.observability import render_metrics
from app.platform.configuration.settings import get_settings

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics(authorization: str = Header(default="")) -> Response:
    settings = get_settings()
    if not settings.observability_enabled or not settings.metrics_token:
        raise HTTPException(404)
    if not compare_digest(authorization, f"Bearer {settings.metrics_token}"):
        raise HTTPException(401, "Invalid monitoring authorization")
    return Response(await render_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")
