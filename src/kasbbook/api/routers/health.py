"""Is this process actually able to do its job?

Two endpoints, deliberately different. `/healthz` answers without touching
anything, so a load balancer can ask it constantly. `/readyz` runs a query,
because a process that cannot reach its database is up but not useful, and
those are the deploys that look fine and are not.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from ..deps import SessionDep
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])

VERSION = "1.0.0-beta.1"


@router.get("/healthz", response_model=HealthResponse)
async def alive() -> HealthResponse:
    return HealthResponse(status="ok", database="not checked", version=VERSION)


@router.get("/readyz", response_model=HealthResponse)
async def ready(session: SessionDep, response: Response) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as error:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="degraded", database=type(error).__name__, version=VERSION
        )
    return HealthResponse(status="ok", database="reachable", version=VERSION)
