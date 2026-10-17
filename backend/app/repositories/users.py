"""User and credential queries (no business rules).

Pre-authentication lookups call the SECURITY DEFINER functions from migration
0002, so they work without a user context and return only the needed columns.
Everything else runs under the caller's row-level-security context.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import cast, column, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import (
    DeviceSeen,
    EmailToken,
    EmailTokenPurpose,
    OtpCode,
    OtpPurpose,
    RecoveryCode,
    Session,
    TotpCredential,
    User,
)


@dataclass(frozen=True)
class LoginRecord:
    """What login needs to know about an account (from `auth_login_lookup`)."""

    id: uuid.UUID
    password_hash: str | None
    role: str
    status: str
    failed_login_count: int
    first_failed_login_at: datetime | None
    locked_until: datetime | None


def _from_function(fn: Any, *names: str) -> Any:
    return select(*(column(n) for n in names)).select_from(fn)


async def create_pending_user(
    db: AsyncSession, *, email: str, phone: str, password_hash: str, role: str, display_name: str
) -> uuid.UUID | None:
    """Insert a PENDING user; None if the email or phone is already taken."""
    # Postgres resolves the function by argument types, so the role is cast to `user_role`.
    role_arg = cast(role, User.__table__.c.role.type)
    result = await db.execute(
        select(func.auth_create_user(email, phone, password_hash, role_arg, display_name))
    )
    value: uuid.UUID | None = result.scalar_one()
    return value


async def login_lookup(db: AsyncSession, email: str) -> LoginRecord | None:
    """Account fields needed to check a login attempt."""
    stmt = _from_function(
        func.auth_login_lookup(email),
        "id", "password_hash", "role", "status", "failed_login_count",
        "first_failed_login_at", "locked_until",
    )  # fmt: skip
    row = (await db.execute(stmt)).mappings().first()
    if row is None:
        return None
    return LoginRecord(
        id=row["id"],
        password_hash=row["password_hash"],
        role=str(row["role"]),
        status=str(row["status"]),
        failed_login_count=int(row["failed_login_count"]),
        first_failed_login_at=row["first_failed_login_at"],
        locked_until=row["locked_until"],
    )


async def record_login_failure(
    db: AsyncSession,
    user_id: uuid.UUID,
    now: datetime,
    *,
    window_seconds: int,
    lock_after: int,
    lock_minutes: int,
) -> tuple[int, datetime | None]:
    """Atomically count a failure; returns (failures in window, locked_until)."""
    stmt = _from_function(
        func.auth_record_login_failure(user_id, now, window_seconds, lock_after, lock_minutes),
        "failed_login_count",
        "locked_until",
    )
    row = (await db.execute(stmt)).mappings().one()
    return int(row["failed_login_count"]), row["locked_until"]


async def user_by_email(db: AsyncSession, email: str) -> tuple[uuid.UUID, str, str] | None:
    """(id, status, display_name) for an email, without revealing anything else."""
    stmt = _from_function(func.auth_user_by_email(email), "id", "status", "display_name")
    row = (await db.execute(stmt)).mappings().first()
    return (row["id"], str(row["status"]), str(row["display_name"])) if row else None


async def consume_email_token(
    db: AsyncSession, token_hash: bytes, purpose: EmailTokenPurpose, now: datetime
) -> uuid.UUID | None:
    """Mark a valid, unexpired token used; return its user id (None if invalid)."""
    purpose_arg = cast(purpose.value, EmailToken.__table__.c.purpose.type)
    result = await db.execute(select(func.auth_consume_email_token(token_hash, purpose_arg, now)))
    value: uuid.UUID | None = result.scalar_one()
    return value


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """The user row (visible only to themselves, admins and SYSTEM under RLS)."""
    return await db.get(User, user_id)


async def add_email_token(
    db: AsyncSession,
    user_id: uuid.UUID,
    purpose: EmailTokenPurpose,
    token_hash: bytes,
    expires_at: datetime,
) -> None:
    """Store a hashed email token."""
    db.add(
        EmailToken(user_id=user_id, purpose=purpose, token_hash=token_hash, expires_at=expires_at)
    )
    await db.flush()


async def invalidate_email_tokens(
    db: AsyncSession, user_id: uuid.UUID, purpose: EmailTokenPurpose, now: datetime
) -> None:
    """Expire outstanding tokens of a purpose (a new link replaces old ones)."""
    await db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )


async def add_otp(
    db: AsyncSession,
    user_id: uuid.UUID,
    purpose: OtpPurpose,
    code_hash: bytes,
    expires_at: datetime,
) -> None:
    """Store a hashed OTP."""
    db.add(OtpCode(user_id=user_id, purpose=purpose, code_hash=code_hash, expires_at=expires_at))
    await db.flush()


async def latest_otp(db: AsyncSession, user_id: uuid.UUID, purpose: OtpPurpose) -> OtpCode | None:
    """Most recent unconsumed OTP (locked for update to count attempts safely)."""
    stmt = (
        select(OtpCode)
        .where(
            OtpCode.user_id == user_id, OtpCode.purpose == purpose, OtpCode.consumed_at.is_(None)
        )
        .order_by(OtpCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def last_otp_sent_at(
    db: AsyncSession, user_id: uuid.UUID, purpose: OtpPurpose
) -> datetime | None:
    """When the latest code was issued (resend throttling)."""
    stmt = select(func.max(OtpCode.created_at)).where(
        OtpCode.user_id == user_id, OtpCode.purpose == purpose
    )
    value: datetime | None = (await db.execute(stmt)).scalar_one()
    return value


async def list_sessions(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> list[Session]:
    """Live sessions of the user, newest activity first."""
    stmt = (
        select(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None), Session.expires_at > now)
        .order_by(Session.last_seen_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    """One session row (RLS hides other users' rows → None)."""
    return await db.get(Session, session_id)


async def totp_credential(db: AsyncSession, user_id: uuid.UUID) -> TotpCredential | None:
    """The admin's TOTP credential, locked for update (replay protection)."""
    stmt = select(TotpCredential).where(TotpCredential.user_id == user_id).with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def unused_recovery_codes(db: AsyncSession, user_id: uuid.UUID) -> list[RecoveryCode]:
    """Recovery codes not yet used (locked for update)."""
    stmt = (
        select(RecoveryCode)
        .where(RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None))
        .with_for_update()
    )
    return list((await db.execute(stmt)).scalars().all())


async def replace_recovery_codes(
    db: AsyncSession, user_id: uuid.UUID, code_hashes: list[str], now: datetime
) -> None:
    """Invalidate old codes and store new ones."""
    await db.execute(
        update(RecoveryCode)
        .where(RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None))
        .values(used_at=now)
    )
    db.add_all(RecoveryCode(user_id=user_id, code_hash=h) for h in code_hashes)
    await db.flush()


async def remember_device(
    db: AsyncSession, user_id: uuid.UUID, fingerprint_hash: bytes, now: datetime
) -> bool:
    """Record a device; True if it was not seen before."""
    stmt = select(DeviceSeen).where(
        DeviceSeen.user_id == user_id, DeviceSeen.fingerprint_hash == fingerprint_hash
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        existing.last_seen = now
        await db.flush()
        return False
    db.add(
        DeviceSeen(
            user_id=user_id, fingerprint_hash=fingerprint_hash, first_seen=now, last_seen=now
        )
    )
    await db.flush()
    return True
