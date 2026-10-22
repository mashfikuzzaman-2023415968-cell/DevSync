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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.context import DbContext
from app.db.session import open_session
from app.models.identity import Notification


async def notify_once(
    db: AsyncSession, user_id: uuid.UUID, kind: str, *, title: str, body: str, link: str
) -> bool:
    """Create a notification unless an unread one of this kind for this link already exists."""
    existing = await db.scalar(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.type == kind,
            Notification.link_path == link,
            Notification.read_at.is_(None),
        )
    )
    if existing is not None:
        return False
    db.add(Notification(user_id=user_id, type=kind, title=title, body=body, link_path=link))
    return True


async def notify_users(
    user_ids: Iterable[uuid.UUID], kind: str, *, title: str, body: str, link: str
) -> int:
    """Notify several users (deduplicated, at most one unread per kind and link) as SYSTEM."""
    unique = list(dict.fromkeys(user_ids))
    if not unique:
        return 0
    created = 0
    async with open_session(DbContext.system(), job=True) as db:
        for user_id in unique:
            created += await notify_once(db, user_id, kind, title=title, body=body, link=link)
        await db.commit()
    return created
