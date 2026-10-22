"""Bidding-deadline job (spec §8, §9.19, §11, §12).

When a project's bidding deadline passes: if there are enough eligible bids to cover the team it
moves `BIDDING → FORMING` (ready for the client to run team formation in Phase 7); otherwise it
stays `BIDDING` and the client is notified of the shortfall with the §9.19 options (extend, lower
standards, raise budget, reduce team, cancel). Runs as SYSTEM in a worker; re-runs are idempotent
(a formed project is no longer BIDDING, and the too-few notification is created at most once).
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from app.core.clock import get_clock
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.projects import Project, ProjectStatus
from app.services import bids as bids_svc
from app.services.notifications import notify_once

log = structlog.get_logger(__name__)

_TOO_FEW = "TOO_FEW_BIDS"
_CLOSED = "BIDDING_CLOSED"


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
            ev = await bids_svc.evaluate(db, project, settings, now.date())
            result = ev.result
            link = f"/client/projects/{project.id}/bids"
            if result.too_few:
                short = ", ".join(
                    f"{c.slot_label or 'a slot'} needs {c.needed - c.eligible} more"
                    for c in bids_svc.coverage(ev)
                    if c.eligible < c.needed
                )
                if await notify_once(
                    db,
                    project.client_id,
                    _TOO_FEW,
                    title="Not enough eligible bids yet",
                    body=f"Bidding closed without enough eligible bids ({short or 'team short'}). "
                    "Extend bidding, lower the minimum standards, raise the budget, reduce the "
                    "team, or cancel.",
                    link=link,
                ):
                    notified_too_few += 1
            else:
                project.status = ProjectStatus.FORMING
                await notify_once(
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
