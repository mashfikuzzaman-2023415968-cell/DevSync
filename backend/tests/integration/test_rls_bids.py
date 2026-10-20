"""Row-level security for sealed bids and reputation snapshots (spec §14.15, §14.13 row 5).

Queries run directly as `devsync_app` (the web role), bypassing the services, to prove the
database itself keeps bids sealed: a bid is visible only to its developer, the project's client
and admins — never to another developer — and reputation snapshots are a public read but
SYSTEM-only to write.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.config import Environment
from app.core.security import hash_password
from app.db.context import DbContext
from app.db.session import open_session
from app.models import User, UserRole, UserStatus
from app.models.bidding import Bid, BidStatus
from app.models.profiles import Skill
from app.models.projects import Project, ProjectSlot, ProjectStatus
from app.models.reputation import ReputationSnapshot
from tests.helpers import stack_available, unique_email, unique_phone

pytestmark = pytest.mark.integration
DbErrors = (ProgrammingError, DBAPIError)


@pytest.fixture(autouse=True)
def _require_stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)


async def make_user(role: str) -> uuid.UUID:
    async with open_session(DbContext.system(), job=True) as db:
        user = User(
            email=unique_email(role.lower()),
            phone_e164=unique_phone() if role != "ADMIN" else None,
            role=UserRole(role),
            status=UserStatus.ACTIVE,
            display_name="RLS",
            password_hash=hash_password("rls test password 1!"),
        )
        db.add(user)
        await db.flush()
        uid = user.id
        await db.commit()
    return uid


def as_user(uid: uuid.UUID, role: str) -> Any:
    return open_session(DbContext(user_id=uid, role=role))


async def make_bidding_project(client_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    async with as_user(client_id, "CLIENT") as db:
        project = Project(
            client_id=client_id,
            title="RLS sealed bids project",
            budget_paisa=1_000_000,
            deadline_days=30,
            team_size=2,
            status=ProjectStatus.BIDDING,
        )
        db.add(project)
        await db.flush()
        skill_id = await db.scalar(select(Skill.id))
        slot = ProjectSlot(project_id=project.id, skill_id=skill_id, count=1)
        db.add(slot)
        await db.flush()
        pid, sid = project.id, slot.id
        await db.commit()
    return pid, sid


async def place_bid(
    developer_id: uuid.UUID, project_id: uuid.UUID, slot_id: uuid.UUID
) -> uuid.UUID:
    async with as_user(developer_id, "DEVELOPER") as db:
        bid = Bid(
            project_id=project_id,
            developer_id=developer_id,
            slot_id=slot_id,
            price_paisa=500_000,
            days_needed=20,
            hours_per_week_committed=20,
            status=BidStatus.ACTIVE,
        )
        db.add(bid)
        await db.flush()
        bid_id = bid.id
        await db.commit()
    return bid_id


@pytest.mark.asyncio
async def test_a_bid_is_sealed_from_other_developers() -> None:
    client = await make_user("CLIENT")
    dev_a = await make_user("DEVELOPER")
    dev_b = await make_user("DEVELOPER")
    admin = await make_user("ADMIN")
    project_id, slot_id = await make_bidding_project(client)
    bid_id = await place_bid(dev_a, project_id, slot_id)

    async with as_user(dev_a, "DEVELOPER") as db:
        assert await db.scalar(select(Bid.id).where(Bid.id == bid_id)) == bid_id
    # The other developer sees nothing of it — not the row, not in any list.
    async with as_user(dev_b, "DEVELOPER") as db:
        assert await db.scalar(select(Bid.id).where(Bid.id == bid_id)) is None
        assert (await db.scalars(select(Bid.id).where(Bid.project_id == project_id))).all() == []
    # The project's client and an admin can read it.
    async with as_user(client, "CLIENT") as db:
        assert await db.scalar(select(Bid.id).where(Bid.id == bid_id)) == bid_id
    async with as_user(admin, "ADMIN") as db:
        assert await db.scalar(select(Bid.id).where(Bid.id == bid_id)) == bid_id
    # A guest sees no bids at all.
    async with open_session(DbContext.guest()) as db:
        assert (await db.scalars(select(Bid.id))).all() == []


@pytest.mark.asyncio
async def test_a_developer_cannot_write_another_developers_bid() -> None:
    client = await make_user("CLIENT")
    dev_a = await make_user("DEVELOPER")
    dev_b = await make_user("DEVELOPER")
    project_id, slot_id = await make_bidding_project(client)
    bid_id = await place_bid(dev_a, project_id, slot_id)

    # dev_b's UPDATE matches no rows (RLS hides the bid), so nothing changes.
    async with as_user(dev_b, "DEVELOPER") as db:
        await db.execute(Bid.__table__.update().where(Bid.id == bid_id).values(price_paisa=1))
        await db.commit()
    async with as_user(dev_a, "DEVELOPER") as db:
        assert await db.scalar(select(Bid.price_paisa).where(Bid.id == bid_id)) == 500_000


@pytest.mark.asyncio
async def test_reputation_snapshot_is_public_read_but_system_write() -> None:
    dev = await make_user("DEVELOPER")
    reader = await make_user("DEVELOPER")
    async with open_session(DbContext.system(), job=True) as db:
        db.add(
            ReputationSnapshot(
                developer_id=dev,
                omega="0.5",
                x="0.5",
                xm="0.5",
                beta="0.6",
                mu="0.5",
                t="0.5",
                c="0.5",
                p="0.55",
            )
        )
        await db.commit()

    # Any authenticated user can read the snapshot (a public value).
    async with as_user(reader, "DEVELOPER") as db:
        assert await db.scalar(
            select(ReputationSnapshot.p).where(ReputationSnapshot.developer_id == dev)
        )
    # The web role cannot write one (SYSTEM only): the INSERT matches no policy → error.
    async with as_user(reader, "DEVELOPER") as db:
        db.add(
            ReputationSnapshot(
                developer_id=reader,
                omega="0.5",
                x="0.5",
                xm="0.5",
                beta="0.6",
                mu="0.5",
                t="0.5",
                c="0.5",
                p="0.55",
            )
        )
        with pytest.raises(DbErrors):
            await db.flush()
