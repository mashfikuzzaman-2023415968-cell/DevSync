"""Bidding-deadline job (spec §8, §9.19, §11, §12).

When a project's bidding deadline passes: if there are enough eligible bids to cover the team it
moves `BIDDING → FORMING` (ready for the client to run team formation in Phase 7); otherwise it
stays `BIDDING` and the client is notified of the shortfall with the §9.19 options (extend, lower
standards, raise budget, reduce team, cancel). A shortfall left alone gets one reminder 7 days
after bidding closed, and the project closes on its own (CANCELLED, free) after 14 days, telling
the client and every bidder (D54). Runs as SYSTEM in a worker; re-runs are idempotent
(a formed project is no longer BIDDING, and the too-few notification is created at most once).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.clock import get_clock
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.projects import Project, ProjectStatus
from app.repositories import bids as bidrepo
from app.services import bids as bids_svc
from app.services.notifications import notify_once

log = structlog.get_logger(__name__)

_TOO_FEW = "TOO_FEW_BIDS"
_REMINDER = "TOO_FEW_BIDS_REMINDER"
_CLOSED = "BIDDING_CLOSED"
_AUTO_CLOSED = "PROJECT_CANCELLED"
AUTO_CLOSE_REASON = "Closed automatically: not enough eligible bids two weeks after bidding closed."


async def close_due_bidding() -> dict[str, int]:
    """Process every BIDDING project whose deadline has passed."""
    moved_to_forming = notified_too_few = auto_closed = 0
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
                    f"{c.slot_label} needs {c.needed - c.eligible} more"
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
                overdue = now - (project.bidding_deadline or now)  # the query excludes None
                if overdue >= bids_svc.AUTO_CLOSE_AFTER:
                    await _auto_close(db, project, now)
                    auto_closed += 1
                elif overdue >= bids_svc.REMIND_AFTER:
                    closes = bids_svc.auto_close_at(project)
                    await notify_once(
                        db,
                        project.client_id,
                        _REMINDER,
                        title="Your project is still short of eligible bids",
                        body=f"“{project.title}” closes automatically on "
                        f"{closes:%d %b %Y} unless you extend bidding, lower the standards, "
                        "raise the budget or reduce the team.",
                        link=link,
                    )
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
    log.info(
        "bidding_deadline_processed",
        formed=moved_to_forming,
        too_few=notified_too_few,
        auto_closed=auto_closed,
    )
    return {"formed": moved_to_forming, "too_few": notified_too_few, "auto_closed": auto_closed}


async def _auto_close(db: AsyncSession, project: Project, now: datetime) -> None:
    """Close an abandoned shortfall (free before a team forms) and tell everyone involved."""
    project.status = ProjectStatus.CANCELLED
    project.cancel_reason = AUTO_CLOSE_REASON
    project.cancelled_at = now
    project.version += 1
    await write_audit(
        db,
        action="project.auto_closed",
        entity_type="project",
        entity_id=project.id,
        actor_role="SYSTEM",
        after={"status": ProjectStatus.CANCELLED.value},
    )
    title = "A project closed for lack of eligible bids"
    body = (
        f"“{project.title}” closed automatically: it was still short of eligible bids two weeks "
        "after bidding closed."
    )
    for user_id, link in [
        (project.client_id, f"/client/projects/{project.id}/bids"),
        *[(dev, "/dev/bids") for dev in await bidrepo.active_bidder_ids(db, project.id)],
    ]:
        await notify_once(db, user_id, _AUTO_CLOSED, title=title, body=body, link=link)


def bidding_deadline() -> dict[str, int]:
    """RQ entry point (sync wrapper)."""
    return asyncio.run(close_due_bidding())
