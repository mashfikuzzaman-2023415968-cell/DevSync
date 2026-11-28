"""In-app notifications (spec §10.2 Notifications, §12, §13.5 #18–19; D122, D153, D162).

Your own only: the list, the unread count, marking read, your §12 switches, and the live
stream. The stream (D107 exactly, as for jobs) needs the session cookie, refuses a foreign
`Origin` or a cross-site `Sec-Fetch-Site` (403) and a user's fourth open stream, jobs streams
included (429). On connect it replays what is newer than `Last-Event-ID` (≤ 50) in one short
session, then forwards what `notify` publishes after each commit; a heartbeat comment every
20 s; it ends after `SSE_MAX_SECONDS` and the browser reconnects with `Last-Event-ID`. It holds
no database connection while open. Events carry only `{id, type, title}`.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import acting, app_settings, require
from app.core.authz import Principal
from app.core.csrf import origin_allowed
from app.core.errors import ErrorCode, ForbiddenError
from app.core.job_events import acquire_stream, release_stream
from app.core.ratelimit import RateLimited
from app.core.redis import get_redis
from app.schemas.common import Page, error_responses
from app.schemas.notifications import (
    EX_NOTIFICATION,
    EX_PREFERENCES,
    NotificationOut,
    Preferences,
    PreferencesUpdate,
    ReadAll,
    UnreadCount,
)
from app.services import notifications as svc
from app.services.context import Ctx

router = APIRouter(tags=["notifications"])
Owner = Annotated[Ctx, Depends(acting("notifications.read"))]
Listener = Annotated[Principal, Depends(require("notifications.read"))]

HEARTBEAT_SECONDS = 20.0
WAIT_SECONDS = 1.0
RETRY_MS = 3000
SAME_SITE = frozenset({"same-origin", "none"})
EVENT_KEYS = ("id", "type", "title")


@router.get(
    "/notifications",
    summary="My notifications",
    response_model=Page[NotificationOut],
    responses={
        200: {"content": {"application/json": {
            "example": {"items": [EX_NOTIFICATION], "next_cursor": None}
        }}},
        **error_responses(401, 403, 404, 422, 429),
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
               **error_responses(401, 403, 404, 429)},
)  # fmt: skip
async def unread_count(ctx: Owner) -> UnreadCount:
    """For the bell's badge."""
    return await svc.unread_count(ctx)


def _event(item: dict[str, Any]) -> str:
    data = json.dumps({k: str(item[k]) for k in EVENT_KEYS}, separators=(",", ":"))
    return f"id: {item['id']}\nevent: notification\ndata: {data}\n\n"


def _parse(raw: Any) -> dict[str, Any] | None:
    """A published message, or None if it isn't exactly `{id, type, title}`."""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict) or set(value) != set(EVENT_KEYS):
        return None
    return value


def _resume_from(last_event_id: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(last_event_id) if last_event_id else None
    except ValueError:
        return None


async def _stream(
    request: Request, principal: Principal, last: uuid.UUID | None, max_seconds: int
) -> AsyncIterator[str]:
    redis = get_redis()
    pubsub = redis.pubsub()
    try:
        # Subscribe before the catch-up query, so nothing committed in between is missed; the
        # catch-up ids are remembered to drop the duplicate the subscription may also bring.
        await pubsub.subscribe(svc.channel(principal.user_id))
        yield f"retry: {RETRY_MS}\n\n"
        replayed: set[str] = set()
        for item in await svc.catch_up(principal.user_id, last, role=principal.role):
            replayed.add(item["id"])
            yield _event(item)
        began = last_beat = time.monotonic()
        while time.monotonic() - began < max_seconds:
            if await request.is_disconnected():
                return
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=WAIT_SECONDS)
            if message is not None and message.get("type") == "message":
                live = _parse(message.get("data"))
                if live is not None and live["id"] not in replayed:
                    yield _event(live)
            if time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
                last_beat = time.monotonic()
                yield ": heartbeat\n\n"
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()  # type: ignore[no-untyped-call]  # redis-py leaves it untyped
        finally:
            await release_stream(redis, principal.user_id)


@router.get(
    "/notifications/stream",
    summary="Live notifications (Server-Sent Events)",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "An event stream of `notification` events with `{id, type, title}`.",
            "content": {"text/event-stream": {"example":
                'id: 5f0c2b7e-3d4a-4e8b-9c1d-2a3b4c5d6e7f\nevent: notification\n'
                'data: {"id":"5f0c2b7e-3d4a-4e8b-9c1d-2a3b4c5d6e7f","type":"MENTIONED",'
                '"title":"Arif Hossain mentioned you"}'}},
        },
        **error_responses(401, 403, 404, 422, 429),
    },
)  # fmt: skip
async def stream(
    request: Request,
    principal: Listener,
    last_event_id: Annotated[str | None, Header(max_length=64)] = None,
    sec_fetch_site: Annotated[str | None, Header(max_length=32)] = None,
) -> StreamingResponse:
    """Your notifications as they happen. Same-origin only; at most 3 open streams per user
    (job streams included)."""
    settings = app_settings(request)
    origin = request.headers.get("origin")
    if (origin is not None and not origin_allowed(origin, None, settings.PUBLIC_ORIGIN)) or (
        sec_fetch_site is not None and sec_fetch_site not in SAME_SITE
    ):
        raise ForbiddenError("Open this page from DevSync.", code=ErrorCode.CSRF_FAILED)
    if not await acquire_stream(get_redis(), principal.user_id):
        raise RateLimited(30)
    return StreamingResponse(
        _stream(request, principal, _resume_from(last_event_id), settings.SSE_MAX_SECONDS),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


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
               **error_responses(401, 404, 429)},
)  # fmt: skip
async def read_all(ctx: Owner) -> ReadAll:
    return await svc.read_all(ctx)


@router.get(
    "/notification-preferences",
    summary="My notification switches",
    response_model=Preferences,
    responses={200: {"content": {"application/json": {"example": EX_PREFERENCES}}},
               **error_responses(401, 403, 404, 429)},
)  # fmt: skip
async def get_preferences(ctx: Owner) -> Preferences:
    """Every §12 row with your in-app and email switches. Account and security emails aren't
    listed: they are always sent."""
    return await svc.get_preferences(ctx)


@router.put(
    "/notification-preferences",
    summary="Change my notification switches",
    response_model=Preferences,
    responses={200: {"content": {"application/json": {"example": EX_PREFERENCES}}},
               **error_responses(401, 403, 404, 422, 429)},
)  # fmt: skip
async def put_preferences(body: PreferencesUpdate, ctx: Owner) -> Preferences:
    """Only the rows you send change. Email can't be switched on where §12 has none (422)."""
    return await svc.put_preferences(ctx, body)
