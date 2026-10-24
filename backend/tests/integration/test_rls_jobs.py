"""Row-level security on `jobs` run records (spec §14.15, migrations 0002 and 0009).

Queries run directly as `devsync_app` (the web role): admins and SYSTEM read every run, a user
reads only the runs they requested, scheduled runs (`requested_by` NULL) are invisible to
ordinary users, and nobody but SYSTEM may change or delete one.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Environment
from app.core.security import hash_password
from app.db.context import DbContext
from app.db.session import open_session
from app.models import User, UserRole, UserStatus
from tests.helpers import stack_available, unique_email, unique_phone

pytestmark = [pytest.mark.integration, pytest.mark.security]
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
            display_name="RLS jobs",
            password_hash=hash_password("rls test password 1!"),
        )
        db.add(user)
        await db.flush()
        uid = user.id
        await db.commit()
    return uid


def as_user(uid: uuid.UUID, role: str) -> Any:
    return open_session(DbContext(user_id=uid, role=role))


INSERT_RUN = text(
    "INSERT INTO jobs (id, type, status, progress, requested_by, created_at, updated_at) "
    "VALUES (gen_random_uuid(), :t, 'RUNNING', 0, :u, now(), now()) RETURNING id"
)


async def _insert_run(db: AsyncSession, job_type: str, requested_by: uuid.UUID | None) -> uuid.UUID:
    job_id = await db.scalar(INSERT_RUN, {"t": job_type, "u": requested_by})
    return uuid.UUID(str(job_id))


async def _visible(db: AsyncSession, job_id: uuid.UUID) -> bool:
    found = await db.scalar(text("SELECT id FROM jobs WHERE id = :id"), {"id": job_id})
    return found is not None


async def test_only_the_requester_admins_and_system_see_a_run() -> None:
    developer, other, admin = (
        await make_user("DEVELOPER"),
        await make_user("CLIENT"),
        await make_user("ADMIN"),
    )
    async with open_session(DbContext.system(), job=True) as db:
        mine = await _insert_run(db, "t.rls.mine", developer)
        scheduled = await _insert_run(db, "t.rls.scheduled", None)
        await db.commit()

    async with as_user(developer, "DEVELOPER") as db:
        assert await _visible(db, mine)
        assert not await _visible(db, scheduled)  # no requester: not theirs
    async with as_user(other, "CLIENT") as db:
        assert not await _visible(db, mine)
        assert not await _visible(db, scheduled)
    async with open_session(DbContext.guest()) as db:
        assert not await _visible(db, mine)
    async with as_user(admin, "ADMIN") as db:
        assert await _visible(db, mine)
        assert await _visible(db, scheduled)
    async with open_session(DbContext.system(), job=True) as db:
        assert await _visible(db, scheduled)


async def test_users_and_admins_cannot_change_or_delete_a_run() -> None:
    developer, admin = await make_user("DEVELOPER"), await make_user("ADMIN")
    async with open_session(DbContext.system(), job=True) as db:
        mine = await _insert_run(db, "t.rls.write", developer)
        await db.commit()

    for uid, role in ((developer, "DEVELOPER"), (admin, "ADMIN")):
        async with as_user(uid, role) as db:
            # UPDATE and DELETE on jobs are SYSTEM-only (0002, 0009): nothing is changed.
            try:
                changed = await db.execute(
                    text("UPDATE jobs SET status = 'SUCCEEDED' WHERE id = :id"), {"id": mine}
                )
                assert changed.rowcount == 0
                removed = await db.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": mine})
                assert removed.rowcount == 0
                await db.commit()
            except DbErrors:  # a revoked privilege is just as good
                await db.rollback()

    async with open_session(DbContext.system(), job=True) as db:
        assert await _visible(db, mine)
        status = await db.scalar(text("SELECT status FROM jobs WHERE id = :id"), {"id": mine})
        assert str(status) == "RUNNING"


async def test_a_user_cannot_record_a_run_for_someone_else() -> None:
    developer, other = await make_user("DEVELOPER"), await make_user("CLIENT")
    async with as_user(developer, "DEVELOPER") as db:
        with pytest.raises(DbErrors):  # the INSERT policy's WITH CHECK refuses it
            await _insert_run(db, "t.rls.forged", other)
        await db.rollback()
