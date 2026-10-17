"""Seeding helpers for the test-only router and `scripts/create_admin.py`.

They run as the worker database role in SYSTEM context (the only context allowed
to insert users directly or create admins under row-level security).
"""

from __future__ import annotations

from typing import Any

import pyotp
from sqlalchemy import select

from app.core.audit import write_audit
from app.core.clock import get_clock
from app.core.config import Settings
from app.core.security import encrypt, generate_recovery_codes, hash_password
from app.db.context import DbContext
from app.db.session import open_session
from app.models.identity import (
    EmailOutbox,
    RecoveryCode,
    TotpCredential,
    User,
    UserRole,
    UserStatus,
)
from app.services.auth.common import totp_key


async def create_user(
    settings: Settings,
    *,
    role: str,
    email: str,
    phone: str | None,
    password: str,
    display_name: str,
    verified: bool,
    with_totp: bool,
    actor: str = "test-seed",
) -> dict[str, Any]:
    """Create a user (ACTIVE when `verified`); admins get TOTP + recovery codes."""
    now = get_clock().now()
    async with open_session(DbContext.system(), job=True) as db:
        user = User(
            email=email,
            phone_e164=phone,
            password_hash=hash_password(password),
            role=UserRole(role),
            status=UserStatus.ACTIVE if verified else UserStatus.PENDING,
            display_name=display_name,
            email_verified_at=now if verified else None,
            phone_verified_at=now if verified and phone else None,
        )
        db.add(user)
        await db.flush()
        result: dict[str, Any] = {
            "user_id": str(user.id),
            "totp_secret": None,
            "recovery_codes": [],
        }
        if role == "ADMIN" and with_totp:
            secret = pyotp.random_base32()
            db.add(
                TotpCredential(
                    user_id=user.id,
                    secret_encrypted=encrypt(
                        totp_key(settings), secret.encode(), str(user.id).encode()
                    ),
                    confirmed_at=now,
                )
            )
            codes = generate_recovery_codes()
            db.add_all(RecoveryCode(user_id=user.id, code_hash=hash_password(c)) for c in codes)
            result.update(totp_secret=secret, recovery_codes=codes)
        await write_audit(
            db,
            action="user.seeded",
            entity_type="user",
            entity_id=user.id,
            actor_role=actor,
            after={"role": role, "verified": verified},
        )
        await db.commit()
    return result


async def latest_email_link(to: str, template: str) -> str | None:
    """The `link` placeholder of the newest outbox email (test environment only)."""
    async with open_session(DbContext.system(), job=True) as db:
        row = (
            await db.execute(
                select(EmailOutbox.payload)
                .where(EmailOutbox.to_email == to, EmailOutbox.template == template)
                .order_by(EmailOutbox.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    link = row.get("link") if isinstance(row, dict) else None
    return str(link) if link else None
