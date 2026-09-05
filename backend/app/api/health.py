from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.application.check_readiness import CheckReadiness, ServiceUnavailableError
from app.application.ports.readiness import ReadinessProbe
from app.bootstrap.dependencies import get_readiness_probe

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    probe: Annotated[ReadinessProbe, Depends(get_readiness_probe)],
) -> dict[str, str]:
    try:
        await CheckReadiness(probe).execute()
    except ServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ready", "database": "ok"}
