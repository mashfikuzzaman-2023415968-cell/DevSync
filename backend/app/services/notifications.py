"""In-app notifications (spec §11, §12): written by the services as SYSTEM, read by their owner
through the Phase 8 read API and page (D122; the live stream arrives in Phase 9).

Notifications are SYSTEM-written (RLS: `notif_insert` allows only `is_system()`, migration 0002),
so a client's action that affects bidders (changed terms, cancellation) writes them through a
SYSTEM session after its own transaction commits — the same pattern as the eligibility
evaluation (DECISIONS D50). Bodies are fixed text plus the recipient's own project data (slot
labels); links are app paths.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import authorize
from app.core.errors import DomainError, ErrorCode, NotFoundError
from app.core.redirects import is_safe_path
from app.db.context import DbContext
from app.db.session import open_session
from app.models.identity import Notification
from app.schemas.common import Page
from app.schemas.notifications import NotificationOut, ReadAll, UnreadCount
from app.services.context import Ctx


def notify(
    db: AsyncSession, user_id: uuid.UUID, kind: str, *, title: str, body: str, link: str
) -> None:
    """Create a notification for a one-off event (no de-duplication)."""
    db.add(Notification(user_id=user_id, type=kind, title=title, body=body, link_path=link))


async def notify_once(
    db: AsyncSession,
    user_id: uuid.UUID,
    kind: str,
    *,
    title: str,
    body: str,
    link: str,
    since: datetime | None = None,
) -> bool:
    """Create a notification unless one of this kind for this link already exists: since
    `since` (read or not) when given, so a repeating job sends it once per occasion; otherwise
    an unread one."""
    conditions = [
        Notification.user_id == user_id,
        Notification.type == kind,
        Notification.link_path == link,
    ]
    if since is not None:
        conditions.append(Notification.created_at >= since)
    else:
        conditions.append(Notification.read_at.is_(None))
    existing = await db.scalar(select(Notification.id).where(*conditions).limit(1))
    if existing is not None:
        return False
    notify(db, user_id, kind, title=title, body=body, link=link)
    return True


async def notify_users(
    user_ids: Iterable[uuid.UUID],
    kind: str,
    *,
    title: str,
    body: str,
    link: str,
    once: bool = True,
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
                created += await notify_once(db, user_id, kind, title=title, body=body, link=link)
            else:
                notify(db, user_id, kind, title=title, body=body, link=link)
                created += 1
        await db.commit()
    return created


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
