"""In-app notifications (spec §11, §12): written by the services as SYSTEM, read by their owner
through the read API and page (D122), and pushed live over SSE (Phase 9, D153, D164).

Notifications are SYSTEM-written (RLS: `notif_insert` allows only `is_system()`, migration 0002),
so a client's action that affects bidders (changed terms, cancellation) writes them through a
SYSTEM session after its own transaction commits — the same pattern as the eligibility
evaluation (DECISIONS D50). Bodies are fixed text plus the recipient's own project data (slot
labels); links are app paths.

Phase 9 (D162–D164, D176):
- Every notification names a `NotificationType` from the catalogue; anything else is refused.
- The recipient's switch for the type's §12 category is honoured: no in-app row when it is off;
  an email that goes with the notification (`EmailSpec`) is queued only when its email switch
  is on (account emails never pass through here and are always sent, `outbox.enqueue`).
- A new notification is published to Redis `notif:{user}` only after its transaction commits
  (a SQLAlchemy `after_commit` listener); a rollback drops it. Only `{id, type, title}` travel.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from redis import Redis as SyncRedis
from redis.exceptions import RedisError
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.authz import authorize
from app.core.config import get_settings
from app.core.errors import DomainError, ErrorCode, NotFoundError
from app.core.logging import get_logger
from app.core.notification_types import CATEGORIES, Category, NotificationType
from app.core.redirects import is_safe_path
from app.db.context import DbContext
from app.db.session import open_session
from app.models.identity import Notification, User, UserStatus
from app.models.workspace import NotificationPreference
from app.schemas.common import Page
from app.schemas.notifications import (
    NotificationOut,
    PreferenceItem,
    Preferences,
    PreferencesUpdate,
    ReadAll,
    UnreadCount,
)
from app.services import outbox
from app.services.context import Ctx
from app.services.notification_prefs import switches

log = get_logger(__name__)

PENDING_KEY = "notif_pending"
CATCH_UP_LIMIT = 50


def channel(user_id: uuid.UUID) -> str:
    """The Redis pub/sub channel of one user's live notifications."""
    return f"notif:{user_id}"


@dataclass(frozen=True)
class EmailSpec:
    """An email that goes with a notification (its template names the type, D163)."""

    template: str
    payload: dict[str, str] = field(default_factory=dict)


async def _exists(
    db: AsyncSession,
    user_id: uuid.UUID,
    kind: NotificationType,
    link: str,
    since: datetime | None,
) -> bool:
    conditions = [
        Notification.user_id == user_id,
        Notification.type == kind.value,
        Notification.link_path == link,
    ]
    if since is not None:
        conditions.append(Notification.created_at >= since)
    else:
        conditions.append(Notification.read_at.is_(None))
    return await db.scalar(select(Notification.id).where(*conditions).limit(1)) is not None


async def _deliver(
    db: AsyncSession,
    user_id: uuid.UUID,
    kind: NotificationType | str,
    *,
    title: str,
    body: str,
    link: str,
    email: EmailSpec | None,
    at: datetime | None = None,
) -> bool:
    """Write the in-app row (unless switched off) and queue its email (if any, and switched
    on). Returns True when something was delivered. `at` stamps the row (a job's watermark)."""
    the_type = NotificationType(kind)  # refuses anything outside the catalogue (D162)
    wants = await switches(user_id, the_type)
    delivered = False
    if wants.in_app:
        row = Notification(
            id=uuid.uuid4(),
            user_id=user_id,
            type=the_type.value,
            title=title,
            body=body,
            link_path=link,
        )
        if at is not None:
            row.created_at = at
        db.add(row)
        db.info.setdefault(PENDING_KEY, []).append(
            {"user_id": str(user_id), "id": str(row.id), "type": the_type.value, "title": title}
        )
        delivered = True
    if email is not None and wants.email:
        user = await db.get(User, user_id)
        if user is not None and user.status == UserStatus.ACTIVE:
            queued = await outbox.enqueue(
                db,
                to=str(user.email),
                template=email.template,
                payload={
                    "name": user.display_name,
                    "link": f"{get_settings().PUBLIC_ORIGIN}{link}",
                    **email.payload,
                },
                user_id=user_id,
            )
            delivered = delivered or queued
    return delivered


async def notify(
    db: AsyncSession,
    user_id: uuid.UUID,
    kind: NotificationType | str,
    *,
    title: str,
    body: str,
    link: str,
    email: EmailSpec | None = None,
    at: datetime | None = None,
) -> bool:
    """Notify about a one-off event (no de-duplication), in the caller's SYSTEM session."""
    return await _deliver(db, user_id, kind, title=title, body=body, link=link, email=email, at=at)


async def notify_once(
    db: AsyncSession,
    user_id: uuid.UUID,
    kind: NotificationType | str,
    *,
    title: str,
    body: str,
    link: str,
    since: datetime | None = None,
    email: EmailSpec | None = None,
) -> bool:
    """Notify unless a notification of this kind for this link already exists: since `since`
    (read or not) when given, so a repeating job sends it once per occasion; otherwise an
    unread one. (With the in-app switch off there is no row to find, so a job run twice for the
    same occasion may email twice; the jobs that pass `since` run once per occasion.)"""
    if await _exists(db, user_id, NotificationType(kind), link, since):
        return False
    return await _deliver(db, user_id, kind, title=title, body=body, link=link, email=email)


async def notify_users(
    user_ids: Iterable[uuid.UUID],
    kind: NotificationType | str,
    *,
    title: str,
    body: str,
    link: str,
    once: bool = True,
    email: EmailSpec | None = None,
) -> int:
    """Notify several users as SYSTEM: at most one unread per kind and link, or (`once=False`)
    every time, for distinct events such as one project being cancelled after another."""
    unique = list(dict.fromkeys(user_ids))
    if not unique:
        return 0
    created = 0
    async with open_session(DbContext.system(), job=True) as db:
        for user_id in unique:
            if once:
                done = await notify_once(
                    db, user_id, kind, title=title, body=body, link=link, email=email
                )
            else:
                done = await notify(
                    db, user_id, kind, title=title, body=body, link=link, email=email
                )
            created += done
        await db.commit()
    return created


# ------------------------------------------------------------------- live publishing (D164)

_publisher: SyncRedis | None = None


def _redis() -> SyncRedis:
    """A small synchronous client: `after_commit` listeners can't await."""
    global _publisher  # noqa: PLW0603 - one lazily created client per process
    if _publisher is None:
        _publisher = SyncRedis.from_url(
            get_settings().REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
    return _publisher


def publish(entries: list[dict[str, Any]]) -> None:
    """Send committed notifications to their owners' channels. Redis being down loses only the
    live push: the rows are stored, and the browser catches up on reconnect or by polling."""
    try:
        client = _redis()
        for entry in entries:
            message = {k: entry[k] for k in ("id", "type", "title")}
            client.publish(
                channel(uuid.UUID(entry["user_id"])), json.dumps(message, separators=(",", ":"))
            )
    except RedisError as exc:
        log.warning("notification_publish_failed", error=type(exc).__name__)


@event.listens_for(Session, "after_commit")
def _publish_after_commit(session: Session) -> None:
    pending = session.info.pop(PENDING_KEY, None)
    if pending:
        publish(pending)


@event.listens_for(Session, "after_rollback")
def _drop_after_rollback(session: Session) -> None:
    session.info.pop(PENDING_KEY, None)


async def catch_up(
    user_id: uuid.UUID, last_id: uuid.UUID | None, *, role: str
) -> list[dict[str, str]]:
    """The caller's notifications newer than `last_id` (oldest first, at most 50), read in one
    short session under their own RLS context. An unknown or foreign id means nothing to resume
    from, so nothing is replayed (the page loads the list itself)."""
    if last_id is None:
        return []
    async with open_session(DbContext(user_id=user_id, role=role)) as db:
        anchor = await db.scalar(
            select(Notification).where(Notification.id == last_id, Notification.user_id == user_id)
        )
        if anchor is None:
            return []
        rows = await db.scalars(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                (Notification.created_at > anchor.created_at)
                | ((Notification.created_at == anchor.created_at) & (Notification.id > anchor.id)),
            )
            .order_by(Notification.created_at, Notification.id)
            .limit(CATCH_UP_LIMIT)
        )
        return [{"id": str(n.id), "type": n.type, "title": n.title} for n in rows]


# ------------------------------------------------------------------- preferences (D162)


async def get_preferences(ctx: Ctx) -> Preferences:
    """Every §12 row with the caller's switches (defaults where they never changed one)."""
    authorize(ctx.principal, "notifications.read")
    rows = await ctx.db.scalars(
        select(NotificationPreference).where(NotificationPreference.user_id == ctx.uid)
    )
    saved = {r.type: r for r in rows}
    items = []
    for cat, info in CATEGORIES.items():
        row = saved.get(cat.value)
        items.append(
            PreferenceItem(
                category=cat.value,
                label=info.label,
                in_app=row.in_app if row is not None else info.in_app,
                email=(row.email if row is not None else info.email) and info.email_available,
                email_available=info.email_available,
            )
        )
    return Preferences(items=items)


async def put_preferences(ctx: Ctx, body: PreferencesUpdate) -> Preferences:
    """Save the given rows (others keep their values). Email can't be switched on where §12
    has no email, and a row can't be listed twice (422)."""
    authorize(ctx.principal, "notifications.read")
    seen: set[str] = set()
    for item in body.items:
        cat = Category(item.category)
        if cat.value in seen:
            raise DomainError(
                "Each kind of notification can appear once.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={"items": f"{cat.value} is listed twice"},
            )
        seen.add(cat.value)
        if item.email and not CATEGORIES[cat].email_available:
            raise DomainError(
                "This kind of notification has no email.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={"items": f"{cat.value} has no email"},
            )
    existing = {
        r.type: r
        for r in await ctx.db.scalars(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == ctx.uid)
            .with_for_update()
        )
    }
    before = {k: {"in_app": r.in_app, "email": r.email} for k, r in existing.items()}
    for item in body.items:
        row = existing.get(item.category)
        if row is None:
            ctx.db.add(
                NotificationPreference(
                    user_id=ctx.uid, type=item.category, in_app=item.in_app, email=item.email
                )
            )
        else:
            row.in_app, row.email, row.updated_at = item.in_app, item.email, ctx.now
    await write_audit(
        ctx.db,
        action="notification_preferences.update",
        entity_type="user",
        entity_id=ctx.uid,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        before=before,
        after={i.category: {"in_app": i.in_app, "email": i.email} for i in body.items},
    )
    await ctx.db.commit()
    return await get_preferences(ctx)


# ------------------------------------------------------------------- reading (Phase 8, D122)


def _encode(at: datetime, nid: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{at.isoformat()}|{nid}".encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        at, nid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        parsed = datetime.fromisoformat(at)
        if parsed.tzinfo is None:
            raise ValueError("naive")
        return parsed, uuid.UUID(nid)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        raise DomainError(
            "That page link is no longer valid.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"cursor": "invalid"},
        ) from None


def _out(n: Notification) -> NotificationOut:
    link = n.link_path if is_safe_path(n.link_path) else None
    return NotificationOut(
        id=n.id,
        type=n.type,
        title=n.title,
        body=n.body,
        link_path=link,
        read_at=n.read_at,
        created_at=n.created_at,
    )


async def list_mine(ctx: Ctx, *, cursor: str | None, limit: int) -> Page[NotificationOut]:
    """The caller's notifications, newest first (RLS: own rows only)."""
    authorize(ctx.principal, "notifications.read")
    stmt = select(Notification).where(Notification.user_id == ctx.uid)
    if cursor is not None:
        at, nid = _decode(cursor)
        stmt = stmt.where(
            (Notification.created_at < at)
            | ((Notification.created_at == at) & (Notification.id < nid))
        )
    rows = list(
        (
            await ctx.db.scalars(
                stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(
                    limit + 1
                )
            )
        ).all()
    )
    nxt = _encode(rows[limit - 1].created_at, rows[limit - 1].id) if len(rows) > limit else None
    return Page[NotificationOut](items=[_out(n) for n in rows[:limit]], next_cursor=nxt)


async def mark_read(ctx: Ctx, notification_id: uuid.UUID) -> NotificationOut:
    authorize(ctx.principal, "notifications.read")
    n = await ctx.db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == ctx.uid
        )
    )
    if n is None:
        raise NotFoundError
    if n.read_at is None:
        n.read_at = ctx.now
        await ctx.db.commit()
        await ctx.db.refresh(n)
    return _out(n)


async def read_all(ctx: Ctx) -> ReadAll:
    authorize(ctx.principal, "notifications.read")
    result = await ctx.db.execute(
        update(Notification)
        .where(Notification.user_id == ctx.uid, Notification.read_at.is_(None))
        .values(read_at=ctx.now)
    )
    await ctx.db.commit()
    return ReadAll(marked=int(result.rowcount or 0))  # type: ignore[attr-defined]


async def unread_count(ctx: Ctx) -> UnreadCount:
    authorize(ctx.principal, "notifications.read")
    n = await ctx.db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == ctx.uid, Notification.read_at.is_(None))
    )
    return UnreadCount(unread=int(n or 0))
