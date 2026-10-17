"""Identity and access tables (spec §7.1) plus notifications and the email outbox (§7.8).

Row-level security policies for these tables are created in migration 0002.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
    column,
    desc,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class UserRole(enum.StrEnum):
    """Primary role chosen at registration (admins are created by admins, §2.1)."""

    CLIENT = "CLIENT"
    DEVELOPER = "DEVELOPER"
    ADMIN = "ADMIN"


class UserStatus(enum.StrEnum):
    """User state machine (§8): PENDING → ACTIVE ↔ SUSPENDED; ACTIVE → DELETED."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class OtpPurpose(enum.StrEnum):
    """Why a phone code was issued."""

    PHONE_VERIFY = "PHONE_VERIFY"
    LOGIN_STEP_UP = "LOGIN_STEP_UP"


class EmailTokenPurpose(enum.StrEnum):
    """Why an email link was issued."""

    VERIFY = "VERIFY"
    RESET = "RESET"


class OutboxStatus(enum.StrEnum):
    """Transactional email outbox state."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class User(UUIDPrimaryKey, Timestamps, Base):
    """An account. Email is case-insensitive; phone is E.164 and unique (one account per phone)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("char_length(display_name) BETWEEN 1 AND 80", name="display_name_length"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_nonneg"),
    )

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    phone_e164: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[UserRole] = mapped_column(_pg_enum(UserRole, "user_role"), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        _pg_enum(UserStatus, "user_status"), nullable=False, server_default="PENDING"
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    first_failed_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Session(UUIDPrimaryKey, Base):
    """Server-side session; the browser only holds an opaque token whose SHA-256 is stored."""

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_revoked", "user_id", "revoked_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    csrf_secret: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    step_up_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    totp_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class OtpCode(UUIDPrimaryKey, Base):
    """Hashed 6-digit phone code: 5-minute expiry, 5 attempts (§14.4)."""

    __tablename__ = "otp_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[OtpPurpose] = mapped_column(_pg_enum(OtpPurpose, "otp_purpose"), nullable=False)
    code_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EmailToken(UUIDPrimaryKey, Base):
    """Single-use email link token (24 h verify, 30 min reset), stored hashed."""

    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[EmailTokenPurpose] = mapped_column(
        _pg_enum(EmailTokenPurpose, "email_token_purpose"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TotpCredential(UUIDPrimaryKey, Timestamps, Base):
    """Admin TOTP secret, AES-GCM encrypted; `last_used_step` blocks replays."""

    __tablename__ = "totp_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    secret_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_step: Mapped[int | None] = mapped_column(BigInteger)


class RecoveryCode(UUIDPrimaryKey, Base):
    """Single-use admin recovery code (Argon2id-hashed)."""

    __tablename__ = "recovery_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DeviceSeen(UUIDPrimaryKey, Base):
    """Known device fingerprints per user (new-device emails; self-dealing signals later)."""

    __tablename__ = "devices_seen"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint_hash", name="uq_devices_seen_user_fp"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Notification(UUIDPrimaryKey, Timestamps, Base):
    """In-app notification (service and UI arrive in Phase 9)."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_user_read_created", "user_id", "read_at", desc(column("created_at"))
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link_path: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailOutbox(UUIDPrimaryKey, Timestamps, Base):
    """Transactional outbox: written in the business transaction, sent by the `email.send` job."""

    __tablename__ = "email_outbox"
    # No implicit RETURNING: web requests may enqueue emails but not read the outbox (RLS).
    __table_args__ = (
        Index("ix_email_outbox_due", "status", "next_attempt_at"),
        {"implicit_returning": False},
    )

    to_email: Mapped[str] = mapped_column(Text, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        _pg_enum(OutboxStatus, "outbox_status"), nullable=False, server_default="PENDING"
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text)
