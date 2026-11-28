"""Discussion endpoints (spec §10.2 "GET/POST /projects/{id}/threads", "GET/POST
/threads/{id}/posts", "PATCH/DELETE /posts/{id}"; D146). Participants only (404 for anyone else;
admins 403 until Phase 12). New threads and posts share the 60/hour `comment` limit with
comments (§14.8)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import acting, only_query, rate_limit
from app.schemas.comments import (
    EX_COMMENT,
    EX_COMMENT_PAGE,
    EX_THREAD,
    EX_THREAD_PAGE,
    CommentOut,
    CommentPatch,
    PostCreate,
    ThreadCreate,
    ThreadOut,
)
from app.schemas.common import Page, error_responses
from app.services import discussion as svc
from app.services.context import Ctx

router = APIRouter(tags=["discussion"])

Reader = Annotated[Ctx, Depends(acting("workspace.read"))]
Writer = Annotated[Ctx, Depends(acting("workspace.write"))]
IfMatch = Annotated[
    int | None, Header(alias="If-Match", ge=0, le=2_147_483_647, description="Post version")
]
Cursor = Annotated[str | None, Query(min_length=1, max_length=300)]
EX_POST = {**EX_COMMENT, "target_type": "DISCUSSION_POST", "target_id": EX_THREAD["id"]}
EX_POST_PAGE = {**EX_COMMENT_PAGE, "items": [EX_POST]}


def _ok(example: object, *errors: int, code: int = 200) -> dict[int | str, dict[str, object]]:
    return {
        code: {"content": {"application/json": {"example": example}}},
        **error_responses(*errors),
    }


@router.get(
    "/projects/{project_id}/threads",
    summary="The project's discussion threads",
    response_model=Page[ThreadOut],
    responses=_ok(EX_THREAD_PAGE, 400, 401, 403, 404, 422, 429),
    dependencies=[Depends(only_query("cursor", "limit"))],
)
async def list_threads(
    project_id: uuid.UUID,
    ctx: Reader,
    cursor: Cursor = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ThreadOut]:
    """Most recently active first."""
    return await svc.list_threads(ctx, project_id, cursor=cursor, limit=limit)


@router.post(
    "/projects/{project_id}/threads",
    summary="Start a thread (participants)",
    status_code=status.HTTP_201_CREATED,
    response_model=ThreadOut,
    responses=_ok(EX_THREAD, 401, 403, 404, 409, 422, 429, code=201),
    dependencies=[Depends(rate_limit("comment"))],
)
async def create_thread(project_id: uuid.UUID, body: ThreadCreate, ctx: Writer) -> ThreadOut:
    """The body becomes the thread's first post; mentions outside the project are dropped."""
    return await svc.create_thread(ctx, project_id, body)


@router.get(
    "/threads/{thread_id}/posts",
    summary="A thread's posts",
    response_model=Page[CommentOut],
    responses=_ok(EX_POST_PAGE, 400, 401, 403, 404, 422, 429),
    dependencies=[Depends(only_query("cursor", "limit"))],
)
async def list_posts(
    thread_id: uuid.UUID,
    ctx: Reader,
    cursor: Cursor = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[CommentOut]:
    """Oldest first. Deleted posts keep their place without their text."""
    return await svc.list_posts(ctx, thread_id, cursor=cursor, limit=limit)


@router.post(
    "/threads/{thread_id}/posts",
    summary="Post in a thread (participants)",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentOut,
    responses=_ok(EX_POST, 401, 403, 404, 409, 422, 429, code=201),
    dependencies=[Depends(rate_limit("comment"))],
)
async def create_post(thread_id: uuid.UUID, body: PostCreate, ctx: Writer) -> CommentOut:
    """A reply names a post of the same thread (422 otherwise)."""
    return await svc.create_post(ctx, thread_id, body)


@router.patch(
    "/posts/{post_id}",
    summary="Edit your post (within 15 minutes)",
    response_model=CommentOut,
    responses=_ok(EX_POST, 401, 403, 404, 409, 422, 429),
)
async def edit_post(
    post_id: uuid.UUID, body: CommentPatch, ctx: Writer, if_match: IfMatch = None
) -> CommentOut:
    """409 `EDIT_WINDOW_CLOSED` after 15 minutes; earlier text is kept for disputes only."""
    return await svc.edit_post(ctx, post_id, body, if_match)


@router.delete(
    "/posts/{post_id}",
    summary="Delete your post",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409, 422, 429),
)
async def delete_post(post_id: uuid.UUID, ctx: Writer, if_match: IfMatch = None) -> Response:
    await svc.delete_post(ctx, post_id, if_match)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
