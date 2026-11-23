"""In-app notifications (spec §10.2 Notifications, §13.5 #18; D122). Your own only; the live
stream and preferences arrive in Phase 9."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import acting
from app.schemas.common import Page, error_responses
from app.schemas.notifications import EX_NOTIFICATION, NotificationOut, ReadAll, UnreadCount
from app.services import notifications as svc
from app.services.context import Ctx

router = APIRouter(tags=["notifications"])
Owner = Annotated[Ctx, Depends(acting("notifications.read"))]


@router.get(
    "/notifications",
    summary="My notifications",
    response_model=Page[NotificationOut],
    responses={
        200: {"content": {"application/json": {
            "example": {"items": [EX_NOTIFICATION], "next_cursor": None}
        }}},
        **error_responses(401, 422, 429),
    },
)  # fmt: skip
async def list_notifications(
    ctx: Owner,
    *,
    cursor: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> Page[NotificationOut]:
    """Newest first, cursor-paged."""
    return await svc.list_mine(ctx, cursor=cursor, limit=limit)


@router.get(
    "/notifications/unread-count",
    summary="How many are unread",
    response_model=UnreadCount,
    responses={200: {"content": {"application/json": {"example": {"unread": 3}}}},
               **error_responses(401, 429)},
)  # fmt: skip
async def unread_count(ctx: Owner) -> UnreadCount:
    """For the bell's badge."""
    return await svc.unread_count(ctx)


@router.post(
    "/notifications/{notification_id}/read",
    summary="Mark one read",
    response_model=NotificationOut,
    responses={200: {"content": {"application/json": {"example": EX_NOTIFICATION}}},
               **error_responses(401, 404, 422, 429)},
)  # fmt: skip
async def mark_read(notification_id: uuid.UUID, ctx: Owner) -> NotificationOut:
    return await svc.mark_read(ctx, notification_id)


@router.post(
    "/notifications/read-all",
    summary="Mark all read",
    response_model=ReadAll,
    responses={200: {"content": {"application/json": {"example": {"marked": 5}}}},
               **error_responses(401, 429)},
)  # fmt: skip
async def read_all(ctx: Owner) -> ReadAll:
    return await svc.read_all(ctx)
