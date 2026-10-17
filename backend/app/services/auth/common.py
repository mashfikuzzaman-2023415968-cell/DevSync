"""Shared pieces of the authentication services: keys, constants, small helpers."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Environment, Settings
from app.core.security import derive_key, hmac_sha256
from app.db.context import DbContext, set_context

OTP_TTL = timedelta(minutes=5)
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60
VERIFY_TOKEN_TTL = timedelta(hours=24)
RESET_TOKEN_TTL = timedelta(minutes=30)
PRE_AUTH_TTL_SECONDS = 300
STEP_UP_TTL = timedelta(minutes=10)
TOTP_INTERVAL = 30
TOTP_ISSUER = "DevSync"


@dataclass(frozen=True)
class AuthDeps:
    """Things every auth flow needs, bundled to keep signatures short."""

    db: AsyncSession
    settings: Settings
    redis: Redis

    @property
    def test_mode(self) -> bool:
        """CAPTCHA bypass / fast challenges are allowed only in the test environment."""
        return self.settings.DEVSYNC_ENV is Environment.TEST


def otp_hash(settings: Settings, user_id: uuid.UUID, code: str) -> bytes:
    """HMAC of the code bound to the user (spec §14.4: OTPs stored hashed with a server key)."""
    return hmac_sha256(derive_key(settings.SECRET_KEY, "otp"), f"{user_id}:{code}")


def totp_key(settings: Settings) -> bytes:
    """AES-GCM key for TOTP secrets."""
    return derive_key(settings.SECRET_KEY, "totp")


def device_fingerprint(user_agent: str | None, ip: str | None) -> bytes:
    """Coarse device fingerprint: browser string + /24 network (no tracking beyond that)."""
    network = ".".join((ip or "").split(".")[:3])
    return hashlib.sha256(f"{(user_agent or '')[:256]}|{network}".encode()).digest()


def verify_link(settings: Settings, token: str) -> str:
    """Absolute link to the email verification screen."""
    return f"{settings.PUBLIC_ORIGIN}/verify-email?token={token}"


def reset_link(settings: Settings, token: str) -> str:
    """Absolute link to the password reset screen."""
    return f"{settings.PUBLIC_ORIGIN}/reset-password?token={token}"


async def act_as(db: AsyncSession, user_id: uuid.UUID, role: str) -> None:
    """Switch the RLS context to a user the flow has just authenticated or created."""
    await set_context(db, DbContext(user_id=user_id, role=role))
