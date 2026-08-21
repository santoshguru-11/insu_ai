"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import SessionDep
from app.schemas.health import HealthResponse
from app.services.health import get_health

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and database connectivity",
)
async def health(session: SessionDep, response: Response) -> HealthResponse:
    """Report application status, environment and database connectivity.

    Returns 503 when the database probe fails so orchestrators treat the
    instance as unhealthy, while the body still describes what is wrong.
    """
    result = await get_health(session)
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
