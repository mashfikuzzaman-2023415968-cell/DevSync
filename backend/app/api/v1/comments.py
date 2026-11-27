"""Comment endpoints (spec §10.2 "GET/POST /comments?target_type=&target_id=" · "PATCH/DELETE
/comments/{id}"; D146). Participants only (404 for anyone else; admins 403 until Phase 12).
Posting shares the 60/hour `comment` limit with discussion posts (§14.8)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import acting, only_query, rate_limit
from app.models.workspace import CommentTarget
from app.schemas.comments import (
    EX_COMMENT,
    EX_COMMENT_PAGE,
    CommentCreate,
    CommentOut,
    CommentPatch,
)
from app.schemas.common import Page, error_responses
from app.services import comments as svc
from app.services.context import Ctx

router = APIRouter(tags=["comments"])

Reader = Annotated[Ctx, Depends(acting("workspace.read"))]
Writer = Annotated[Ctx, Depends(acting("workspace.write"))]
IfMatch = Annotated[
    int | None, Header(alias="If-Match", ge=0, le=2_147_483_647, description="Comment version")
]


def _ok(example: object, *errors: int, code: int = 200) -> dict[int | str, dict[str, object]]:
    return {
        code: {"content": {"application/json": {"example": example}}},
        **error_responses(*errors),
    }


@router.get(
    "/comments",
    summary="A task's, milestone's or check-in's comments",
    response_model=Page[CommentOut],
    responses=_ok(EX_COMMENT_PAGE, 400, 401, 403, 404, 422, 429),
    dependencies=[Depends(only_query("target_type", "target_id", "cursor", "limit"))],
)
async def list_comments(
    ctx: Reader,
    target_type: CommentTarget,
    target_id: uuid.UUID,
    cursor: Annotated[str | None, Query(min_length=1, max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[CommentOut]:
    """Oldest first. Deleted comments keep their place without their text."""
    return await svc.list_comments(ctx, target_type, target_id, cursor=cursor, limit=limit)


@router.post(
    "/comments",
    summary="Comment (participants)",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentOut,
    responses=_ok(EX_COMMENT, 401, 403, 404, 409, 422, 429, code=201),
    dependencies=[Depends(rate_limit("comment"))],
)
async def create_comment(body: CommentCreate, ctx: Writer) -> CommentOut:
    """Mentions of people outside the project are dropped; at most 10 (422 above)."""
    return await svc.create_comment(ctx, body)


@router.patch(
    "/comments/{comment_id}",
    summary="Edit your comment (within 15 minutes)",
    response_model=CommentOut,
    responses=_ok(EX_COMMENT, 401, 403, 404, 409, 422, 429),
)
async def edit_comment(
    comment_id: uuid.UUID, body: CommentPatch, ctx: Writer, if_match: IfMatch = None
) -> CommentOut:
    """409 `EDIT_WINDOW_CLOSED` after 15 minutes; earlier text is kept for disputes only."""
    return await svc.edit_comment(ctx, comment_id, body, if_match)


@router.delete(
    "/comments/{comment_id}",
    summary="Delete your comment",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409, 422, 429),
)
async def delete_comment(comment_id: uuid.UUID, ctx: Writer, if_match: IfMatch = None) -> Response:
    await svc.delete_comment(ctx, comment_id, if_match)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
