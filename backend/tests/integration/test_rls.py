"""Row-level security as the second gate (spec §14.15, §16.4 "Row-level security").

Every test connects as `devsync_app` (the web role) and queries the tables
**directly**, bypassing service-level checks, to prove the database itself
refuses cross-user access.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import column, func, insert, select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.config import Environment
from app.core.security import hash_password, token_digest
from app.db.context import DbContext, set_context
from app.db.session import open_session
from app.models import (
    DeviceSeen,
    EmailOutbox,
    EmailToken,
    EmailTokenPurpose,
    IdempotencyKey,
    Job,
    Notification,
    OtpCode,
    OtpPurpose,
    PlatformSettings,
    RecoveryCode,
    Session,
    TotpCredential,
    User,
    UserRole,
    UserStatus,
)
from tests.helpers import stack_available, unique_email

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)


async def _make_user(role: str = "CLIENT") -> uuid.UUID:
    async with open_session(DbContext.system(), job=True) as db:
        user = User(
            email=unique_email(),
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


async def _seed_rows(owner: uuid.UUID) -> None:
    """One row per user-owned table for `owner` (as SYSTEM)."""
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    now = datetime.now(UTC)
    async with open_session(DbContext.system(), job=True) as db:
        db.add_all(
            [
                Session(
                    user_id=owner,
                    token_hash=token_digest(uuid.uuid4().hex),
                    csrf_secret=b"c" * 32,
                    expires_at=now + timedelta(days=1),
                ),
                OtpCode(
                    user_id=owner, purpose=OtpPurpose.PHONE_VERIFY, code_hash=b"h", expires_at=now
                ),
                EmailToken(
                    user_id=owner,
                    purpose=EmailTokenPurpose.VERIFY,
                    token_hash=token_digest(uuid.uuid4().hex),
                    expires_at=now,
                ),
                TotpCredential(user_id=owner, secret_encrypted=b"x" * 40),
                RecoveryCode(user_id=owner, code_hash="h"),
                DeviceSeen(user_id=owner, fingerprint_hash=uuid.uuid4().bytes),
                IdempotencyKey(
                    user_id=owner, key=str(uuid.uuid4()), request_hash=b"r", expires_at=now
                ),
                Notification(user_id=owner, type="t", title="t", body="b"),
                Job(type="t", requested_by=owner),
            ]
        )
        await db.commit()


@pytest.fixture
async def two_users() -> tuple[uuid.UUID, uuid.UUID]:
    a, b = await _make_user(), await _make_user()
    await _seed_rows(a)
    await _seed_rows(b)
    return a, b


OWNED: list[tuple[type[Any], str]] = [
    (Session, "user_id"),
    (OtpCode, "user_id"),
    (EmailToken, "user_id"),
    (TotpCredential, "user_id"),
    (RecoveryCode, "user_id"),
    (DeviceSeen, "user_id"),
    (IdempotencyKey, "user_id"),
    (Notification, "user_id"),
    (Job, "requested_by"),
]


@pytest.mark.parametrize(("model", "owner_col"), OWNED, ids=[m.__tablename__ for m, _ in OWNED])
async def test_users_see_only_their_own_rows(
    two_users: tuple[uuid.UUID, uuid.UUID], model: type[Any], owner_col: str
) -> None:
    a, b = two_users
    async with open_session(DbContext(user_id=a, role="CLIENT")) as db:
        owners = set((await db.execute(select(getattr(model, owner_col)))).scalars().all())
    assert b not in owners
    assert a in owners


@pytest.mark.parametrize(("model", "owner_col"), OWNED, ids=[m.__tablename__ for m, _ in OWNED])
async def test_guest_sees_nothing(
    two_users: tuple[uuid.UUID, uuid.UUID], model: type[Any], owner_col: str
) -> None:
    async with open_session(DbContext.guest()) as db:
        rows = (await db.execute(select(getattr(model, owner_col)))).scalars().all()
    assert rows == []


async def test_users_table_is_own_row_only(two_users: tuple[uuid.UUID, uuid.UUID]) -> None:
    a, _b = two_users
    async with open_session(DbContext(user_id=a, role="CLIENT")) as db:
        ids = set((await db.execute(select(User.id))).scalars().all())
    assert ids == {a}


async def test_admin_can_read_users_but_not_private_credentials(
    two_users: tuple[uuid.UUID, uuid.UUID],
) -> None:
    a, b = two_users
    admin = await _make_user("ADMIN")
    async with open_session(DbContext(user_id=admin, role="ADMIN")) as db:
        ids = set((await db.execute(select(User.id))).scalars().all())
        totp_owners = set((await db.execute(select(TotpCredential.user_id))).scalars().all())
    assert {a, b} <= ids
    assert totp_owners.isdisjoint({a, b})


async def test_cross_user_update_and_delete_affect_nothing(
    two_users: tuple[uuid.UUID, uuid.UUID],
) -> None:
    a, b = two_users
    async with open_session(DbContext(user_id=a, role="CLIENT")) as db:
        updated = await db.execute(
            text("UPDATE sessions SET revoked_at = now() WHERE user_id = :b"), {"b": b}
        )
        deleted = await db.execute(text("DELETE FROM recovery_codes WHERE user_id = :b"), {"b": b})
        await db.commit()
    assert updated.rowcount == 0  # type: ignore[attr-defined]
    assert deleted.rowcount == 0  # type: ignore[attr-defined]


async def test_cannot_insert_rows_for_another_user(two_users: tuple[uuid.UUID, uuid.UUID]) -> None:
    a, b = two_users
    async with open_session(DbContext(user_id=a, role="CLIENT")) as db:
        with pytest.raises((ProgrammingError, DBAPIError), match="row-level security"):
            await db.execute(insert(RecoveryCode).values(user_id=b, code_hash="forged"))


async def test_web_role_cannot_claim_system_context(two_users: tuple[uuid.UUID, uuid.UUID]) -> None:
    async with open_session(DbContext.system()) as db:  # devsync_app connection, role SYSTEM
        rows = (await db.execute(select(Session.user_id))).scalars().all()
        with pytest.raises((ProgrammingError, DBAPIError)):
            await db.execute(
                insert(User).values(
                    email=unique_email(), role="ADMIN", status="ACTIVE", display_name="evil"
                )
            )
    assert rows == []


async def test_web_role_cannot_create_users_directly() -> None:
    async with open_session(DbContext.guest()) as db:
        with pytest.raises((ProgrammingError, DBAPIError)):
            await db.execute(
                insert(User).values(
                    email=unique_email(), role="CLIENT", status="ACTIVE", display_name="direct"
                )
            )


async def test_registration_function_refuses_admin_role() -> None:
    from app.repositories.users import create_pending_user  # noqa: PLC0415

    async with open_session(DbContext.guest()) as db:
        with pytest.raises((ProgrammingError, DBAPIError), match="cannot create role"):
            await create_pending_user(
                db,
                email=unique_email(),
                phone="+8801700000001",
                password_hash="h",
                role="ADMIN",
                display_name="x",
            )


async def test_definer_functions_return_only_needed_columns() -> None:
    uid = await _make_user()
    async with open_session(DbContext.guest()) as db:
        email = (
            await db.execute(text("SELECT email FROM users WHERE id = :i"), {"i": uid})
        ).scalar()
        assert email is None  # the table itself is invisible to guests
        cols = (
            await db.execute(
                select(column("id"), column("status"), column("display_name")).select_from(
                    func.auth_user_by_email("nobody@example.com")
                )
            )
        ).keys()
    assert list(cols) == ["id", "status", "display_name"]


async def test_settings_table_admin_only_but_active_settings_readable() -> None:
    async with open_session(DbContext.guest()) as db:
        assert (await db.execute(select(PlatformSettings.version))).scalars().all() == []
        version = (
            await db.execute(select(column("version")).select_from(func.active_settings()))
        ).scalar()
    assert version is not None
    assert version >= 2


async def test_outbox_is_write_only_for_web_requests() -> None:
    async with open_session(DbContext.guest()) as db:
        await db.execute(
            insert(EmailOutbox).values(
                to_email="a@example.com", template="verify_email", payload={}
            )
        )
        visible = (await db.execute(select(EmailOutbox.id))).scalars().all()
        await db.rollback()
    assert visible == []


async def test_audit_log_append_only_and_admin_read(two_users: tuple[uuid.UUID, uuid.UUID]) -> None:
    a, _b = two_users
    async with open_session(DbContext(user_id=a, role="CLIENT")) as db:
        await db.execute(
            text("INSERT INTO audit_log (action, entity_type) VALUES ('rls.test', 'x')")
        )
        assert (await db.execute(text("SELECT count(*) FROM audit_log"))).scalar() == 0
        await db.commit()
    admin = await _make_user("ADMIN")
    async with open_session(DbContext(user_id=admin, role="ADMIN")) as db:
        assert (
            await db.execute(text("SELECT count(*) FROM audit_log WHERE action='rls.test'"))
        ).scalar() >= 1
        assert (await db.execute(select(func.audit_verify_chain()))).scalar() is None


async def test_context_switch_applies_inside_a_transaction() -> None:
    a = await _make_user()
    async with open_session(DbContext.guest()) as db:
        assert (await db.execute(select(User.id).where(User.id == a))).scalar() is None
        await set_context(db, DbContext(user_id=a, role="CLIENT"))
        assert (await db.execute(select(User.id).where(User.id == a))).scalar() == a
