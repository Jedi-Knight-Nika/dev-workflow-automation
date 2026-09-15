from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.bootstrap.dependencies import get_deployment_queries
from app.delivery.application.deployments import DeploymentQueries
from app.interfaces.http.errors import service_errors

router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.get("")
async def deployment_history(
    start: datetime,
    end: datetime,
    repository_id: UUID | None = None,
    limit: int = Query(default=1000, ge=1, le=2000),
    queries: DeploymentQueries = Depends(get_deployment_queries),
) -> dict[str, Any]:
    with service_errors(value_status=422):
        return await queries.history(start, end, repository_id, limit)
