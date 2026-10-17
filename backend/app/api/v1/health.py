"""Health endpoints (spec §15.6).

`/health` is liveness: no dependencies, always cheap. `/health/ready` checks that
PostgreSQL, Redis and the job queue are reachable; Nginx blocks it from the
outside (internal network only, §10.2).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.schemas.common import error_responses
from app.services import health as health_service

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness result."""

    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    """Readiness result per dependency."""

    status: Literal["ok", "unavailable"]
    checks: dict[str, Literal["ok", "unavailable"]]


@router.get(
    "/health",
    summary="Liveness check",
    response_model=HealthResponse,
    responses={200: {"content": {"application/json": {"example": {"status": "ok"}}}}},
)
async def health() -> HealthResponse:
    """Return ok while the process is serving requests."""
    return HealthResponse(status="ok")


@router.get(
    "/health/ready",
    summary="Readiness check (internal network only)",
    response_model=ReadinessResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "checks": {"database": "ok", "redis": "ok", "queue": "ok"},
                    }
                }
            }
        },
        **error_responses(503),
    },
)
async def ready() -> JSONResponse:
    """Report whether every dependency answers; 503 if any does not."""
    checks = await health_service.check_dependencies()
    ok = all(v == "ok" for v in checks.values())
    body = ReadinessResponse(status="ok" if ok else "unavailable", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)
