"""In-app notifications for the bidding flow (spec §11; the inbox UI arrives in Phase 9).

Notifications are SYSTEM-written (RLS: `notif_insert` allows only `is_system()`, migration 0002),
so a client's action that affects bidders (changed terms, cancellation) writes them through a
SYSTEM session after its own transaction commits — the same pattern as the eligibility
evaluation (DECISIONS D50). Bodies are fixed text plus the recipient's own project data (slot
labels); links are app paths.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.context import DbContext
from app.db.session import open_session
from app.models.identity import Notification


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
