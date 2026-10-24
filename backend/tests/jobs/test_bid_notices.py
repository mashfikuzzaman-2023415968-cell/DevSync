"""Client notices about bids (spec §11, §12): the hourly "new bids" notice, the daily digest
email, and the emails for "bidding closed" / "too few bids". Every job is idempotent."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update

from app.db.context import DbContext
from app.db.session import open_session
from app.jobs.bid_notice_jobs import digest_window, notify_new_bids, send_bid_digests
from app.jobs.bidding_jobs import close_due_bidding
from app.models import User, UserStatus
from app.models.bidding import Bid, BidStatus
from app.models.identity import EmailOutbox, Notification
from tests.jobs.test_bidding_deadline import (
    just_closed,
    make_eligible_bidder,
    make_project,
    make_user,
)

pytestmark = [pytest.mark.jobs, pytest.mark.integration]

SOON = timedelta(minutes=5)  # "the job runs a little later", past the settle minute


async def _notices(user_id: uuid.UUID, kind: str = "NEW_BIDS") -> list[tuple[str, str | None]]:
    """(title, link) of the user's notices of `kind`, oldest first."""
    async with open_session(DbContext.system(), job=True) as db:
        rows = await db.execute(
            select(Notification.title, Notification.link_path)
            .where(Notification.user_id == user_id, Notification.type == kind)
            .order_by(Notification.created_at)
        )
        return [(t, link) for t, link in rows]


async def _emails(user_id: uuid.UUID, template: str) -> list[dict[str, Any]]:
    """Payloads of the outbox emails to the user with `template`."""
    async with open_session(DbContext.system(), job=True) as db:
        user = await db.get(User, user_id)
        assert user is not None
        rows = await db.scalars(
            select(EmailOutbox.payload).where(
                EmailOutbox.to_email == str(user.email), EmailOutbox.template == template
            )
        )
        return [dict(p) for p in rows]


async def _open_project(client: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    return await make_project(client, datetime.now(UTC) + timedelta(days=3))


# --------------------------------------------------------------------------- hourly notice


@pytest.mark.asyncio
async def test_new_bids_become_one_notice_and_a_rerun_adds_nothing() -> None:
    client = await make_user("CLIENT")
    pid, sid, skid = await _open_project(client)
    await make_eligible_bidder(pid, sid, skid)
    await make_eligible_bidder(pid, sid, skid)

    await notify_new_bids(datetime.now(UTC) + SOON)
    assert await _notices(client) == [
        ("2 new bids on your project", f"/client/projects/{pid}/bids")
    ]

    await notify_new_bids(datetime.now(UTC) + SOON)  # same hour again: nothing new
    assert len(await _notices(client)) == 1


@pytest.mark.asyncio
async def test_only_bids_since_the_last_notice_are_counted() -> None:
    client = await make_user("CLIENT")
    pid, sid, skid = await _open_project(client)
    await make_eligible_bidder(pid, sid, skid)
    await make_eligible_bidder(pid, sid, skid)
    await notify_new_bids(datetime.now(UTC) + SOON)
    # A later bid, seen by the next hourly run.
    later = await make_eligible_bidder(pid, sid, skid)
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(
            update(Bid)
            .where(Bid.developer_id == later)
            .values(created_at=datetime.now(UTC) + SOON + timedelta(minutes=30))
        )
        await db.commit()
    await notify_new_bids(datetime.now(UTC) + SOON + timedelta(hours=1))
    notices = await _notices(client)
    assert [title for title, _link in notices] == [
        "2 new bids on your project",
        "1 new bid on your project",
    ]


@pytest.mark.asyncio
async def test_a_bid_in_the_settle_minute_waits_for_the_next_run() -> None:
    client = await make_user("CLIENT")
    pid, sid, skid = await _open_project(client)
    await make_eligible_bidder(pid, sid, skid)
    await notify_new_bids(datetime.now(UTC))  # cut-off is a minute ago: the bid is too new
    assert await _notices(client) == []
    await notify_new_bids(datetime.now(UTC) + SOON)
    assert len(await _notices(client)) == 1


@pytest.mark.asyncio
async def test_withdrawn_bids_closed_projects_and_suspended_clients_get_nothing() -> None:
    client = await make_user("CLIENT")
    pid, sid, skid = await _open_project(client)
    dev = await make_eligible_bidder(pid, sid, skid)
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(
            update(Bid).where(Bid.developer_id == dev).values(status=BidStatus.WITHDRAWN)
        )
        await db.commit()
    await notify_new_bids(datetime.now(UTC) + SOON)
    assert await _notices(client) == []

    suspended = await make_user("CLIENT")
    pid2, sid2, skid2 = await _open_project(suspended)
    await make_eligible_bidder(pid2, sid2, skid2)
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(
            update(User).where(User.id == suspended).values(status=UserStatus.SUSPENDED)
        )
        await db.commit()
    await notify_new_bids(datetime.now(UTC) + SOON)
    assert await _notices(suspended) == []


# --------------------------------------------------------------------------- daily digest


def test_the_digest_covers_the_previous_dhaka_day() -> None:
    # 01:30 on 25 Oct in Dhaka is 19:30 UTC on 24 Oct: the digest is for 24 Oct (Dhaka).
    day, start, end = digest_window(datetime(2026, 10, 24, 19, 30, tzinfo=UTC))
    assert day == "2026-10-24"
    assert start == datetime(2026, 10, 23, 18, 0, tzinfo=UTC)
    assert end - start == timedelta(days=1)
    # One minute before Dhaka midnight it is still 24 Oct there: digest for 23 Oct.
    assert digest_window(datetime(2026, 10, 24, 17, 59, tzinfo=UTC))[0] == "2026-10-23"


@pytest.mark.asyncio
async def test_one_digest_per_client_per_day() -> None:
    client = await make_user("CLIENT")
    pid, sid, skid = await _open_project(client)
    await make_eligible_bidder(pid, sid, skid)
    await make_eligible_bidder(pid, sid, skid)
    tomorrow = datetime.now(UTC) + timedelta(days=1)  # the digest of "today"

    await send_bid_digests(tomorrow)
    [email] = await _emails(client, "new_bids_digest")
    assert "“Deadline job project” 2 bids" in email["summary"]
    assert email["link"].endswith("/client/projects")

    await send_bid_digests(tomorrow)  # re-run or a second scheduler: no second email
    assert len(await _emails(client, "new_bids_digest")) == 1
    await send_bid_digests(datetime.now(UTC))  # "today's" bids are not in yesterday's digest
    assert len(await _emails(client, "new_bids_digest")) == 1


@pytest.mark.asyncio
async def test_no_bids_no_digest() -> None:
    client = await make_user("CLIENT")
    await _open_project(client)
    await send_bid_digests(datetime.now(UTC) + timedelta(days=1))
    assert await _emails(client, "new_bids_digest") == []


# --------------------------------------------------------------------------- deadline emails


@pytest.mark.asyncio
async def test_too_few_bids_is_emailed_once() -> None:
    client = await make_user("CLIENT")
    await make_project(client, just_closed())
    await close_due_bidding()
    await close_due_bidding()
    [email] = await _emails(client, "too_few_bids")
    assert email["project"] == "Deadline job project"
    assert "needs 2 more" in email["shortfall"]


@pytest.mark.asyncio
async def test_bidding_closed_is_emailed_once() -> None:
    client = await make_user("CLIENT")
    pid, sid, skid = await make_project(client, just_closed())
    await make_eligible_bidder(pid, sid, skid)
    await make_eligible_bidder(pid, sid, skid)
    await close_due_bidding()
    await close_due_bidding()
    [email] = await _emails(client, "bidding_closed")
    assert email["link"].endswith(f"/client/projects/{pid}/bids")


@pytest.mark.asyncio
async def test_a_suspended_client_is_not_emailed() -> None:
    client = await make_user("CLIENT")
    await make_project(client, just_closed())
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(update(User).where(User.id == client).values(status=UserStatus.SUSPENDED))
        await db.commit()
    await close_due_bidding()
    assert await _emails(client, "too_few_bids") == []
