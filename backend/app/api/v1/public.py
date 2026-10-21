"""Public homepage data and client error reports (spec §13.11, §15.7)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from redis.asyncio import Redis

from app.api.deps import DbSession, principal_of, rate_limit, redis_client
from app.core.errors import DomainError, ErrorCode
from app.schemas.common import Page, error_responses
from app.schemas.marketplace import ProjectCard, ProjectDetail
from app.schemas.public import ClientErrorReport, PublicStats
from app.services import marketplace as market
from app.services.client_errors import record_client_error
from app.services.public_stats import get_public_stats

router = APIRouter(tags=["public"])

MAX_REPORT_BYTES = 8 * 1024


@router.get(
    "/public/stats",
    summary="Live numbers for the homepage",
    response_model=PublicStats,
    response_model_exclude_none=True,
    dependencies=[Depends(rate_limit("public_stats"))],
    responses={
        200: {"content": {"application/json": {"example": {"developers": 42}}}},
        **error_responses(429),
    },
)
async def public_stats(
    db: DbSession, redis: Annotated[Redis, Depends(redis_client)], response: Response
) -> PublicStats:
    """Aggregate counts only, cached for 5 minutes; absent numbers are omitted."""
    response.headers["Cache-Control"] = "public, max-age=300"
    return await get_public_stats(db, redis)


def _limit_body(request: Request) -> None:
    length = request.headers.get("content-length")
    if length is None or not length.isdigit() or int(length) > MAX_REPORT_BYTES:
        raise DomainError(code=ErrorCode.PAYLOAD_TOO_LARGE)


@router.post(
    "/client-errors",
    summary="Report a frontend error",
    status_code=204,
    dependencies=[Depends(_limit_body), Depends(rate_limit("client_errors"))],
    responses={**error_responses(403, 413, 422, 429)},
)
async def client_errors(request: Request, report: ClientErrorReport) -> Response:
    """Sanitized and logged for the team; nothing is stored or returned."""
    p = principal_of(request)
    record_client_error(report, str(p.user_id) if p else None)
    return Response(status_code=204)


@router.get(
    "/public/projects",
    summary="Public list of open projects",
    response_model=Page[ProjectCard],
    responses={
        200: {"content": {"application/json": {"example": {"items": [], "next_cursor": None}}}},
        **error_responses(422),
    },
)
async def public_projects(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=200)] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ProjectCard]:
    """Open projects for anyone (limited columns, never any bid data)."""
    return await market.search(db, q=q, cursor=cursor, limit=limit)


@router.get(
    "/public/projects/{project_id}",
    summary="Public view of one open project",
    response_model=ProjectDetail,
    responses={
        200: {"content": {"application/json": {"example": {}}}},
        **error_responses(404, 422),
    },
)
async def public_project(db: DbSession, project_id: uuid.UUID) -> ProjectDetail:
    return await market.get_public(db, project_id)
