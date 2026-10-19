"""Row-level security for the project tables (spec §14.15, §14.13 row 4).

Queries run directly as `devsync_app` (the web role), bypassing the services, to prove the
database itself keeps projects apart: a DRAFT project is private to its client, a non-DRAFT
project is readable by everyone (the marketplace), and no one but the owning client may write.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.config import Environment
from app.core.security import hash_password
from app.db.context import DbContext
from app.db.session import open_session
from app.models import User, UserRole, UserStatus
from app.models.profiles import Skill
from app.models.projects import PlanBaseline, Project, ProjectSlot, ProjectStatus
from tests.helpers import stack_available, unique_email, unique_phone

pytestmark = pytest.mark.integration
DbErrors = (ProgrammingError, DBAPIError)


@pytest.fixture(autouse=True)
def _require_stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)


async def make_user(role: str = "CLIENT") -> uuid.UUID:
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


def as_user(uid: uuid.UUID, role: str = "CLIENT") -> Any:
    return open_session(DbContext(user_id=uid, role=role))


async def make_project(client_id: uuid.UUID, status: ProjectStatus) -> uuid.UUID:
    async with as_user(client_id, "CLIENT") as db:
        project = Project(
            client_id=client_id,
            title="RLS sample project",
            budget_paisa=1_000_000,
            deadline_days=30,
            team_size=2,
            status=status,
        )
        db.add(project)
        await db.flush()
        pid = project.id
        await db.commit()
    return pid


@pytest.mark.asyncio
async def test_draft_is_private_but_bidding_is_public() -> None:
    owner = await make_user("CLIENT")
    other = await make_user("CLIENT")
    developer = await make_user("DEVELOPER")
    draft = await make_project(owner, ProjectStatus.DRAFT)
    bidding = await make_project(owner, ProjectStatus.BIDDING)

    async with as_user(owner, "CLIENT") as db:
        visible = set((await db.scalars(select(Project.id))).all())
    assert {draft, bidding} <= visible

    for viewer, role in ((other, "CLIENT"), (developer, "DEVELOPER")):
        async with as_user(viewer, role) as db:
            ids = set((await db.scalars(select(Project.id))).all())
        assert bidding in ids, "a non-DRAFT project is visible to everyone"
        assert draft not in ids, "a DRAFT project is private to its client"

    async with open_session(DbContext.guest()) as db:
        guest_ids = set((await db.scalars(select(Project.id))).all())
    assert bidding in guest_ids
    assert draft not in guest_ids


@pytest.mark.asyncio
async def test_non_owner_cannot_write_a_project() -> None:
    owner = await make_user("CLIENT")
    other = await make_user("CLIENT")
    draft = await make_project(owner, ProjectStatus.DRAFT)

    # An update as another client matches no rows (RLS hides them), so nothing changes.
    async with as_user(other, "CLIENT") as db:
        await db.execute(update(Project).where(Project.id == draft).values(title="hijacked xyz"))
        await db.commit()
    async with as_user(owner, "CLIENT") as db:
        title = await db.scalar(select(Project.title).where(Project.id == draft))
    assert title == "RLS sample project"


@pytest.mark.asyncio
async def test_child_rows_follow_project_visibility() -> None:
    owner = await make_user("CLIENT")
    other = await make_user("CLIENT")
    draft = await make_project(owner, ProjectStatus.DRAFT)
    bidding = await make_project(owner, ProjectStatus.BIDDING)

    async with as_user(owner, "CLIENT") as db:
        skill_id = await db.scalar(select(Skill.id))
        db.add_all(
            [
                ProjectSlot(project_id=draft, skill_id=skill_id, count=2),
                ProjectSlot(project_id=bidding, skill_id=skill_id, count=2),
            ]
        )
        await db.commit()

    async with as_user(other, "CLIENT") as db:
        slot_projects = set((await db.scalars(select(ProjectSlot.project_id))).all())
    assert bidding in slot_projects
    assert draft not in slot_projects


@pytest.mark.asyncio
async def test_plan_baseline_is_owner_only() -> None:
    owner = await make_user("CLIENT")
    other = await make_user("CLIENT")
    bidding = await make_project(owner, ProjectStatus.BIDDING)
    async with as_user(owner, "CLIENT") as db:
        db.add(PlanBaseline(project_id=bidding, version=1, cpm={"duration": 10}))
        await db.commit()

    async with as_user(owner, "CLIENT") as db:
        assert await db.scalar(select(PlanBaseline.id).where(PlanBaseline.project_id == bidding))
    async with as_user(other, "CLIENT") as db:
        # Even though the project is public, its baseline plan is not.
        assert (
            await db.scalar(select(PlanBaseline.id).where(PlanBaseline.project_id == bidding))
        ) is None
