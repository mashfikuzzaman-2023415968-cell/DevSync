"""New-bid notices for clients (spec §12 "New bid on your project (batched hourly)", in-app, and
a daily digest email; §11 rules: idempotent, re-load everything from the database).

- `notify_new_bids` (hourly): for each project open for bids, the bids placed since the last
  "new bids" notice become one in-app notice ("3 new bids on …"). The notice's own `created_at`
  is the watermark: it is set to the cut-off the job counted up to (a minute before it runs, so
  a bid still being committed is counted next time), and a re-run finds nothing new.
- `send_bid_digests` (daily, 08:00 Asia/Dhaka): one email per client summarising the bids placed
  on their projects during the previous Dhaka calendar day. The outbox row carries the day, so a
  re-run (or a second scheduler) never emails twice for the same day.

Both run as SYSTEM (bids and notifications are not readable or writable by other roles here);
they reveal only counts to the project's own client, who can see the bids anyway (sealed, §14.5).
Withdrawn bids are not counted. Suspended or deleted clients get nothing.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import structlog
from sqlalchemy import func, select

from app.core.clock import DISPLAY_TZ, get_clock
from app.core.config import get_settings
from app.db.context import DbContext
from app.db.locks import advisory_xact_lock
from app.db.session import open_session
from app.models.bidding import Bid, BidStatus
from app.models.identity import EmailOutbox, Notification, User, UserStatus
from app.models.projects import Project, ProjectStatus
from app.services import outbox

log = structlog.get_logger(__name__)

NEW_BIDS = "NEW_BIDS"
DIGEST_TEMPLATE = "new_bids_digest"
# Bids committed slightly after they were stamped are counted on the next run, never lost.
SETTLE = timedelta(minutes=1)
# How far back the hourly job looks for a project's first notice (a project's bids before that
# are summarised by the daily digest anyway).
LOOKBACK = timedelta(days=7)
DIGEST_MAX_PROJECTS = 5


def _bids_link(project_id: uuid.UUID) -> str:
    return f"/client/projects/{project_id}/bids"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


async def notify_new_bids(now: datetime | None = None) -> dict[str, int]:
    """One in-app notice per project with bids placed since its last notice."""
    now = now or get_clock().now()
    cutoff = now - SETTLE
    created = 0
    async with open_session(DbContext.system(), job=True) as db:
        projects = (
            await db.execute(
                select(Project.id, Project.client_id, Project.title)
                .join(Bid, Bid.project_id == Project.id)
                .where(
                    Project.status == ProjectStatus.BIDDING,
                    Bid.status != BidStatus.WITHDRAWN,
                    Bid.created_at > cutoff - LOOKBACK,
                    Bid.created_at <= cutoff,
                )
                .distinct()
            )
        ).all()
    for project_id, client_id, title in projects:
        link = _bids_link(project_id)
        async with open_session(DbContext.system(), job=True) as db:
            client = await db.get(User, client_id)
            if client is None or client.status != UserStatus.ACTIVE:
                continue
            # Serialize concurrent runs for this client (a second scheduler, a retry).
            await advisory_xact_lock(db, project_id)
            watermark = await db.scalar(
                select(func.max(Notification.created_at)).where(
                    Notification.user_id == client_id,
                    Notification.type == NEW_BIDS,
                    Notification.link_path == link,
                )
            )
            since = max(watermark, cutoff - LOOKBACK) if watermark else cutoff - LOOKBACK
            count = int(
                await db.scalar(
                    select(func.count())
                    .select_from(Bid)
                    .where(
                        Bid.project_id == project_id,
                        Bid.status != BidStatus.WITHDRAWN,
                        Bid.created_at > since,
                        Bid.created_at <= cutoff,
                    )
                )
                or 0
            )
            if count == 0:
                continue
            db.add(
                Notification(
                    user_id=client_id,
                    type=NEW_BIDS,
                    title=f"{_plural(count, 'new bid')} on your project",
                    body=f"“{title}” received {_plural(count, 'new sealed bid')}. "
                    "Open the bids to see who qualifies.",
                    link_path=link,
                    created_at=cutoff,  # the watermark the next run counts from
                )
            )
            await db.commit()
            created += 1
    log.info("new_bid_notices", created=created)
    return {"notified": created}


def digest_window(now: datetime) -> tuple[str, datetime, datetime]:
    """The previous Dhaka calendar day as (ISO date, start UTC, end UTC)."""
    today = now.astimezone(DISPLAY_TZ).date()
    day = today - timedelta(days=1)
    start = datetime.combine(day, time.min, tzinfo=DISPLAY_TZ)
    return day.isoformat(), start, start + timedelta(days=1)


async def send_bid_digests(now: datetime | None = None) -> dict[str, int]:
    """Email each client a summary of yesterday's new bids (Dhaka day), once per day."""
    now = now or get_clock().now()
    day, start, end = digest_window(now)
    async with open_session(DbContext.system(), job=True) as db:
        rows = (
            await db.execute(
                select(Project.client_id, Project.id, Project.title, func.count(Bid.id))
                .join(Bid, Bid.project_id == Project.id)
                .where(
                    Bid.status != BidStatus.WITHDRAWN,
                    Bid.created_at >= start,
                    Bid.created_at < end,
                    Project.status != ProjectStatus.CANCELLED,
                )
                .group_by(Project.client_id, Project.id, Project.title)
            )
        ).all()
    by_client: dict[uuid.UUID, list[tuple[str, int]]] = defaultdict(list)
    for client_id, _pid, title, count in rows:
        by_client[client_id].append((title, int(count)))
    sent = 0
    label = date.fromisoformat(day).strftime("%d %b %Y")
    for client_id, projects in by_client.items():
        async with open_session(DbContext.system(), job=True) as db:
            client = await db.get(User, client_id)
            if client is None or client.status != UserStatus.ACTIVE:
                continue
            await advisory_xact_lock(db, client_id)
            already = await db.scalar(
                select(EmailOutbox.id)
                .where(
                    EmailOutbox.template == DIGEST_TEMPLATE,
                    EmailOutbox.to_email == str(client.email),
                    EmailOutbox.payload["digest_date"].astext == day,
                )
                .limit(1)
            )
            if already is not None:
                continue
            projects.sort(key=lambda p: (-p[1], p[0].casefold()))
            parts = [f"“{t}” {_plural(n, 'bid')}" for t, n in projects[:DIGEST_MAX_PROJECTS]]
            if len(projects) > DIGEST_MAX_PROJECTS:
                parts.append(f"and {_plural(len(projects) - DIGEST_MAX_PROJECTS, 'more project')}")
            await outbox.enqueue(
                db,
                to=str(client.email),
                template=DIGEST_TEMPLATE,
                payload={
                    "name": client.display_name,
                    "date": label,
                    "summary": "; ".join(parts),
                    "link": f"{get_settings().PUBLIC_ORIGIN}/client/projects",
                    "digest_date": day,
                },
            )
            await db.commit()
            sent += 1
    log.info("new_bid_digests", sent=sent, day=day)
    return {"sent": sent}


def new_bid_notices() -> dict[str, int]:
    """RQ entry point (sync wrapper)."""
    return asyncio.run(notify_new_bids())


def bid_digests() -> dict[str, int]:
    """RQ entry point (sync wrapper)."""
    return asyncio.run(send_bid_digests())
