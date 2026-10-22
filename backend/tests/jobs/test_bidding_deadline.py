"""The bidding-deadline job (spec §8, §9.19, §12): close due projects, notify, stay idempotent."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.core.config import Environment
from app.core.security import hash_password
from app.db.context import DbContext
from app.db.session import open_session
from app.jobs.bidding_jobs import close_due_bidding
from app.models import User, UserRole, UserStatus
from app.models.bidding import Bid, BidStatus
from app.models.identity import Notification
from app.models.profiles import DeveloperSkill, Skill
from app.models.projects import Project, ProjectSlot, ProjectStatus
from app.models.reputation import ReputationSnapshot
from tests.helpers import stack_available, unique_email, unique_phone

pytestmark = [pytest.mark.jobs, pytest.mark.integration]


def just_closed() -> datetime:
    """A deadline that passed an hour ago (before the reminder and auto-close windows)."""
    return datetime.now(UTC) - timedelta(hours=1)


@pytest.fixture(autouse=True)
def _stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
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
            display_name="Job",
            password_hash=hash_password("job test password 1!"),
        )
        db.add(user)
        await db.flush()
        uid = user.id
        await db.commit()
    return uid


def as_user(uid: uuid.UUID, role: str) -> Any:
    return open_session(DbContext(user_id=uid, role=role))


async def make_project(
    client_id: uuid.UUID, deadline: datetime | None
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with as_user(client_id, "CLIENT") as db:
        project = Project(
            client_id=client_id,
            title="Deadline job project",
            budget_paisa=10_000_000,
            deadline_days=30,
            team_size=2,
            status=ProjectStatus.BIDDING,
            bidding_deadline=deadline,
        )
        db.add(project)
        await db.flush()
        skill_id = await db.scalar(select(Skill.id))
        slot = ProjectSlot(project_id=project.id, skill_id=skill_id, count=2)
        db.add(slot)
        await db.flush()
        pid, sid, skid = project.id, slot.id, skill_id
        await db.commit()
    return pid, sid, skid


async def make_eligible_bidder(
    project_id: uuid.UUID, slot_id: uuid.UUID, skill_id: uuid.UUID
) -> uuid.UUID:
    dev = await make_user("DEVELOPER")
    async with open_session(DbContext.system(), job=True) as db:
        db.add(
            ReputationSnapshot(
                developer_id=dev,
                omega="0.7",
                x="0.8",
                xm="0.7",
                beta="0.8",
                mu="0.7",
                t="0.7",
                c="0.78",
                p="0.80",
                completed_projects=5,
                distinct_clients=4,
            )
        )
        await db.commit()
    async with as_user(dev, "DEVELOPER") as db:
        db.add(DeveloperSkill(user_id=dev, skill_id=skill_id, self_level=4))
        db.add(
            Bid(
                project_id=project_id,
                developer_id=dev,
                slot_id=slot_id,
                price_paisa=500_000,
                days_needed=20,
                hours_per_week_committed=20,
                status=BidStatus.ACTIVE,
            )
        )
        await db.commit()
    return dev


async def _notifications(client_id: uuid.UUID, kind: str) -> int:
    async with open_session(DbContext.system(), job=True) as db:
        rows = await db.scalars(
            select(Notification.id).where(
                Notification.user_id == client_id, Notification.type == kind
            )
        )
        return len(rows.all())


async def _status(project_id: uuid.UUID) -> ProjectStatus:
    async with open_session(DbContext.system(), job=True) as db:
        return await db.scalar(select(Project.status).where(Project.id == project_id))


@pytest.mark.asyncio
async def test_too_few_bids_stays_bidding_notifies_once() -> None:
    client = await make_user("CLIENT")
    pid, _sid, _sk = await make_project(client, just_closed())  # no bids

    first = await close_due_bidding()
    assert first["too_few"] >= 1
    assert await _status(pid) == ProjectStatus.BIDDING
    assert await _notifications(client, "TOO_FEW_BIDS") == 1

    # Idempotent: a second run does not create a duplicate notification.
    await close_due_bidding()
    assert await _notifications(client, "TOO_FEW_BIDS") == 1


@pytest.mark.asyncio
async def test_too_few_notification_names_the_shortfall_per_slot() -> None:
    client = await make_user("CLIENT")
    await make_project(client, just_closed())  # one unlabelled slot needing 2, no bids
    await close_due_bidding()
    async with open_session(DbContext.system(), job=True) as db:
        body = await db.scalar(
            select(Notification.body).where(
                Notification.user_id == client, Notification.type == "TOO_FEW_BIDS"
            )
        )
    assert body is not None
    assert "needs 2 more" in body  # the slot is named by its skill when it has no label
    assert "Extend bidding" in body


@pytest.mark.asyncio
async def test_enough_bids_moves_to_forming() -> None:
    client = await make_user("CLIENT")
    pid, sid, skid = await make_project(client, just_closed())
    await make_eligible_bidder(pid, sid, skid)
    await make_eligible_bidder(pid, sid, skid)

    result = await close_due_bidding()
    assert result["formed"] >= 1
    assert await _status(pid) == ProjectStatus.FORMING
    assert await _notifications(client, "BIDDING_CLOSED") == 1


@pytest.mark.asyncio
async def test_future_deadline_is_left_alone() -> None:
    client = await make_user("CLIENT")
    future = datetime.now(UTC) + timedelta(days=5)
    pid, _sid, _sk = await make_project(client, future)
    await close_due_bidding()
    assert await _status(pid) == ProjectStatus.BIDDING


@pytest.mark.asyncio
async def test_a_shortfall_left_alone_gets_one_reminder_after_a_week() -> None:
    client = await make_user("CLIENT")
    pid, _sid, _sk = await make_project(client, datetime.now(UTC) - timedelta(days=8))
    await close_due_bidding()
    await close_due_bidding()
    assert await _status(pid) == ProjectStatus.BIDDING
    assert await _notifications(client, "TOO_FEW_BIDS_REMINDER") == 1
    async with open_session(DbContext.system(), job=True) as db:
        body = await db.scalar(
            select(Notification.body).where(
                Notification.user_id == client, Notification.type == "TOO_FEW_BIDS_REMINDER"
            )
        )
    assert body is not None
    assert "closes automatically on" in body


@pytest.mark.asyncio
async def test_a_shortfall_left_alone_for_two_weeks_closes_and_tells_everyone() -> None:
    client = await make_user("CLIENT")
    pid, sid, skid = await make_project(client, datetime.now(UTC) - timedelta(days=15))
    dev = await make_eligible_bidder(pid, sid, skid)  # one of the two places

    first = await close_due_bidding()
    assert first["auto_closed"] >= 1
    assert await _status(pid) == ProjectStatus.CANCELLED
    async with open_session(DbContext.system(), job=True) as db:
        project = await db.get(Project, pid)
        assert project is not None
        assert project.cancel_reason is not None
        assert project.cancel_reason.startswith("Closed automatically")
        assert project.cancelled_at is not None
    assert await _notifications(client, "PROJECT_CANCELLED") == 1
    assert await _notifications(dev, "PROJECT_CANCELLED") == 1

    # A cancelled project is no longer BIDDING: a re-run changes nothing.
    await close_due_bidding()
    assert await _notifications(client, "PROJECT_CANCELLED") == 1


@pytest.mark.asyncio
async def test_a_covered_team_is_formed_however_late_the_job_runs() -> None:
    client = await make_user("CLIENT")
    pid, sid, skid = await make_project(client, datetime.now(UTC) - timedelta(days=30))
    await make_eligible_bidder(pid, sid, skid)
    await make_eligible_bidder(pid, sid, skid)
    await close_due_bidding()
    assert await _status(pid) == ProjectStatus.FORMING
