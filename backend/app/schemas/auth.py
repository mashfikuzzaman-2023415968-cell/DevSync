"""Request/response models for accounts and authentication (spec §10.2 Auth, Me).

Requests reject unknown fields (mass-assignment defence): a client can never
send `role=ADMIN`, `status`, `email_verified_at` and so on.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import StrictRequest

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
OTP = re.compile(r"^\d{6}$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _clean_name(value: str) -> str:
    value = unicodedata.normalize("NFC", CONTROL.sub("", value)).strip()
    if not 1 <= len(value) <= 80:  # noqa: PLR2004 - spec §7.1 display_name 1–80
        raise ValueError("Use 1 to 80 characters.")
    return value


class BotCheck(StrictRequest):
    """Fields every public form carries (spec §14.16)."""

    captcha: str | None = Field(default=None, max_length=4096)
    website: str | None = Field(default=None, max_length=200, description="Honeypot; leave empty.")
    started_at_ms: int | None = Field(default=None, ge=0, description="When the form was shown.")


class RegisterRequest(BotCheck):
    """Self-registration (CLIENT or DEVELOPER only; admins are created by admins)."""

    display_name: str = Field(min_length=1, max_length=80)
    email: EmailStr = Field(max_length=254)
    phone: str = Field(max_length=16, description="E.164, e.g. +8801712345678")
    password: str = Field(min_length=1, max_length=128)
    role: Literal["CLIENT", "DEVELOPER"]
    accept_terms: Literal[True]

    _name = field_validator("display_name")(_clean_name)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        value = value.replace(" ", "").replace("-", "")
        if not E164.fullmatch(value):
            raise ValueError("Use international format, e.g. +8801712345678.")
        return value


class AcceptedResponse(BaseModel):
    """Uniform 202 answer that never reveals whether an account exists."""

    message: str


class LoginRequest(BotCheck):
    """Email + password (+ CAPTCHA after repeated failures, and always for admins)."""

    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)
    return_to: str | None = Field(default=None, max_length=512)


class LoginResponse(BaseModel):
    """Either a signed-in session (cookie set) or a TOTP step for admins."""

    status: Literal["SIGNED_IN", "TOTP_REQUIRED", "TOTP_SETUP_REQUIRED"]
    redirect_to: str | None = None
    pre_auth: str | None = None


class TotpLoginRequest(StrictRequest):
    """Second factor for admins: a 6-digit code or a recovery code."""

    pre_auth: str = Field(min_length=20, max_length=100)
    code: str | None = Field(default=None, pattern=r"^\d{6}$")
    recovery_code: str | None = Field(default=None, min_length=8, max_length=20)
    return_to: str | None = Field(default=None, max_length=512)


class CodeRequest(StrictRequest):
    """A 6-digit code (phone OTP, TOTP confirm, step-up)."""

    code: str = Field(pattern=r"^\d{6}$")


class EmailTokenRequest(StrictRequest):
    """Token from an email link."""

    token: str = Field(min_length=20, max_length=100)


class ForgotPasswordRequest(BotCheck):
    """Start a password reset (always answered uniformly)."""

    email: EmailStr = Field(max_length=254)


class ResetPasswordRequest(StrictRequest):
    """Finish a password reset."""

    token: str = Field(min_length=20, max_length=100)
    new_password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(StrictRequest):
    """Change password while signed in."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class SessionInfo(BaseModel):
    """One device/session in the security list."""

    id: uuid.UUID
    current: bool
    ip: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime


class SessionList(BaseModel):
    """All live sessions of the caller."""

    items: list[SessionInfo]


class TotpSetupResponse(BaseModel):
    """Provisioning URI for an authenticator app (shown once)."""

    provisioning_uri: str
    secret: str


class RecoveryCodesResponse(BaseModel):
    """Single-use recovery codes (shown once)."""

    recovery_codes: list[str]


class MeResponse(BaseModel):
    """The caller's own account (never includes hashes or secrets)."""

    id: uuid.UUID
    email: str
    phone_e164: str | None
    display_name: str
    role: Literal["CLIENT", "DEVELOPER", "ADMIN"]
    status: Literal["PENDING", "ACTIVE"]
    email_verified: bool
    phone_verified: bool
    totp_enabled: bool
    totp_verified: bool
    created_at: datetime


class MeUpdateRequest(StrictRequest):
    """Fields a user may change themselves in Phase 1."""

    display_name: str = Field(min_length=1, max_length=80)

    _name = field_validator("display_name")(_clean_name)


class CaptchaChallenge(BaseModel):
    """ALTCHA v1 challenge."""

    algorithm: Literal["SHA-256"]
    challenge: str
    max_number: int
    salt: str
    signature: str


class AdminSessionResponse(BaseModel):
    """Admin's own security status (also proves the admin area is hidden from others)."""

    user_id: uuid.UUID
    totp_verified: bool
    step_up_active: bool
