"""Bidding-deadline job (spec §8, §9.19, §11, §12).

When a project's bidding deadline passes: if there are enough eligible bids to cover the team it
moves `BIDDING → FORMING` (ready for the client to run team formation in Phase 7); otherwise it
stays `BIDDING` and the client is notified of the shortfall with the §9.19 options (extend, lower
standards, raise budget, reduce team, cancel). Runs as SYSTEM in a worker; re-runs are idempotent
(a formed project is no longer BIDDING, and the too-few notification is created at most once).
"""

from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import get_clock
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.identity import Notification
from app.models.projects import Project, ProjectStatus
from app.services import bids as bids_svc

log = structlog.get_logger(__name__)

_TOO_FEW = "TOO_FEW_BIDS"
_CLOSED = "BIDDING_CLOSED"


async def _notify_once(
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


async def close_due_bidding() -> dict[str, int]:
    """Process every BIDDING project whose deadline has passed."""
    moved_to_forming = notified_too_few = 0
    async with open_session(DbContext.system(), job=True) as db:
        settings = await active_settings(db)
        now = get_clock().now()
        projects = (
            await db.scalars(
                select(Project).where(
                    Project.status == ProjectStatus.BIDDING,
                    Project.bidding_deadline.is_not(None),
                    Project.bidding_deadline <= now,
                )
            )
        ).all()
        for project in projects:
            _bids, result, _reps = await bids_svc.evaluate_project(
                db, project, settings, now.date()
            )
            link = f"/client/projects/{project.id}/bids"
            if result.too_few:
                if await _notify_once(
                    db,
                    project.client_id,
                    _TOO_FEW,
                    title="Not enough eligible bids yet",
                    body="Bidding closed without enough eligible bids. Extend bidding, lower the "
                    "minimum standards, raise the budget, reduce the team, or cancel.",
                    link=link,
                ):
                    notified_too_few += 1
            else:
                project.status = ProjectStatus.FORMING
                await _notify_once(
                    db,
                    project.client_id,
                    _CLOSED,
                    title="Bidding closed — ready to form your team",
                    body="You have enough eligible bids. Start team formation to build your team.",
                    link=link,
                )
                moved_to_forming += 1
        await db.commit()
    log.info("bidding_deadline_processed", formed=moved_to_forming, too_few=notified_too_few)
    return {"formed": moved_to_forming, "too_few": notified_too_few}


def bidding_deadline() -> dict[str, int]:
    """RQ entry point (sync wrapper)."""
    return asyncio.run(close_due_bidding())
