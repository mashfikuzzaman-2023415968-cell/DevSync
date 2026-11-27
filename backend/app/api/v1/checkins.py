"""Weekly check-in endpoints (spec §10.2 Check-ins; D145). Members post one per week; the client
and members read the feed (404 for anyone outside the project)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import acting, only_query
from app.schemas.checkins import EX_CHECKIN, EX_FEED, CheckinCreate, CheckinFeed, CheckinOut
from app.schemas.common import error_responses
from app.services import checkins as svc
from app.services.context import Ctx

router = APIRouter(tags=["check-ins"])

Reader = Annotated[Ctx, Depends(acting("workspace.read"))]
Poster = Annotated[Ctx, Depends(acting("workspace.checkin.post"))]


def _ok(example: object, *errors: int, code: int = 200) -> dict[int | str, dict[str, object]]:
    return {
        code: {"content": {"application/json": {"example": example}}},
        **error_responses(*errors),
    }


@router.get(
    "/projects/{project_id}/checkins",
    summary="The project's weekly check-ins",
    response_model=CheckinFeed,
    responses=_ok(EX_FEED, 400, 401, 403, 404, 422, 429),
    dependencies=[Depends(only_query("member_id", "cursor", "limit"))],
)
async def checkin_feed(
    project_id: uuid.UUID,
    ctx: Reader,
    member_id: uuid.UUID | None = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CheckinFeed:
    """Newest week first; `this_week` says who still owes one (due Tuesday 23:59 Dhaka)."""
    return await svc.feed(ctx, project_id, member_id=member_id, cursor=cursor, limit=limit)


@router.post(
    "/projects/{project_id}/checkins",
    summary="Post this week's check-in (members)",
    status_code=status.HTTP_201_CREATED,
    response_model=CheckinOut,
    responses=_ok(EX_CHECKIN, 401, 403, 404, 409, 422, 429, code=201),
)
async def post_checkin(project_id: uuid.UUID, body: CheckinCreate, ctx: Poster) -> CheckinOut:
    """One per member per week (409 `CHECKIN_EXISTS`); immutable once posted."""
    return await svc.post_checkin(ctx, project_id, body)
