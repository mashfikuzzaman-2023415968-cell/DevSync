"""Registration and verification (spec §14.4, §8 User).

Registration answers uniformly whether or not the email/phone is taken; the
owner of an existing account gets a notice email instead. New accounts are
PENDING until both the phone (6-digit OTP) and the email (link) are verified,
then become ACTIVE.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.core.audit import write_audit
from app.core.authz import Principal
from app.core.errors import DomainError, ErrorCode
from app.core.ratelimit import RateLimited
from app.core.security import (
    constant_time_equals,
    generate_otp,
    generate_token,
    hash_password,
    password_problems,
    token_digest,
)
from app.core.sessions import SessionPolicy, SessionStore
from app.integrations.sms import sms_sender
from app.models.identity import EmailTokenPurpose, OtpPurpose, User, UserStatus
from app.repositories import users as repo
from app.services import outbox
from app.services.auth.common import (
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_SECONDS,
    OTP_TTL,
    VERIFY_TOKEN_TTL,
    AuthDeps,
    act_as,
    otp_hash,
    verify_link,
)

UNIFORM_MESSAGE = "Check your email and phone to verify your account."


def reject_weak_password(password: str, user_inputs: list[str]) -> None:
    """Raise a 422 with the policy problems, if any."""
    problems = password_problems(password, user_inputs)
    if problems:
        raise DomainError(
            "Choose a stronger password.",
            code=ErrorCode.PASSWORD_REJECTED,
            fields={"password": " ".join(problems)},
        )


async def register(
    deps: AuthDeps,
    now: datetime,
    *,
    display_name: str,
    email: str,
    phone: str,
    password: str,
    role: str,
) -> None:
    """Create a PENDING account (or quietly notify the existing owner). Commits."""
    reject_weak_password(password, [email, display_name, phone])
    password_hash = hash_password(password)  # always hashed: uniform timing
    db = deps.db
    user_id = await repo.create_pending_user(
        db,
        email=email,
        phone=phone,
        password_hash=password_hash,
        role=role,
        display_name=display_name,
    )
    if user_id is None:
        existing = await repo.user_by_email(db, email)
        if existing is not None:
            await outbox.enqueue(
                db,
                to=email,
                template="account_exists",
                payload={"name": existing[2], "link": f"{deps.settings.PUBLIC_ORIGIN}/login"},
            )
        await write_audit(db, action="auth.register_duplicate", entity_type="user", entity_id=None)
        await db.commit()
        return

    await act_as(db, user_id, role)
    await _issue_email_token(deps, user_id, display_name, email, now)
    code = await _issue_otp(deps, user_id, now)
    await write_audit(
        db,
        action="auth.register",
        entity_type="user",
        entity_id=user_id,
        actor_id=user_id,
        actor_role=role,
        after={"role": role, "status": "PENDING"},
    )
    await db.commit()
    await sms_sender(deps.settings, deps.redis).send(phone, f"Your DevSync code is {code}")


async def _issue_email_token(
    deps: AuthDeps, user_id: uuid.UUID, name: str, email: str, now: datetime
) -> None:
    token = generate_token(32)
    await repo.invalidate_email_tokens(deps.db, user_id, EmailTokenPurpose.VERIFY, now)
    await repo.add_email_token(
        deps.db, user_id, EmailTokenPurpose.VERIFY, token_digest(token), now + VERIFY_TOKEN_TTL
    )
    await outbox.enqueue(
        deps.db,
        to=email,
        template="verify_email",
        payload={"name": name, "link": verify_link(deps.settings, token)},
    )


async def _issue_otp(deps: AuthDeps, user_id: uuid.UUID, now: datetime) -> str:
    code = generate_otp()
    await repo.add_otp(
        deps.db,
        user_id,
        OtpPurpose.PHONE_VERIFY,
        otp_hash(deps.settings, user_id, code),
        now + OTP_TTL,
    )
    return code


async def _load_self(deps: AuthDeps, principal: Principal) -> User:
    user = await repo.get_user(deps.db, principal.user_id)
    if user is None:
        raise DomainError(code=ErrorCode.UNAUTHENTICATED)
    return user


async def _activate_if_complete(deps: AuthDeps, user: User, now: datetime) -> None:
    if (
        user.status == UserStatus.PENDING
        and user.email_verified_at is not None
        and user.phone_verified_at is not None
    ):
        user.status = UserStatus.ACTIVE
        # Live sessions cached "PENDING"; update them so the user needn't sign in again.
        await SessionStore(deps.redis, SessionPolicy(deps.settings)).refresh_status(
            user.id, UserStatus.ACTIVE.value
        )
        await write_audit(
            deps.db,
            action="user.activate",
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
            actor_role=str(user.role),
            before={"status": "PENDING"},
            after={"status": "ACTIVE"},
        )


async def send_phone_otp(deps: AuthDeps, principal: Principal, now: datetime) -> None:
    """Send a new phone code (60-second resend cooldown). Commits."""
    user = await _load_self(deps, principal)
    if user.phone_verified_at is not None:
        raise DomainError(code=ErrorCode.ALREADY_VERIFIED)
    if user.phone_e164 is None:
        raise DomainError("Add a phone number first.", code=ErrorCode.INVALID_STATE)
    last = await repo.last_otp_sent_at(deps.db, user.id, OtpPurpose.PHONE_VERIFY)
    if last is not None and (now - last).total_seconds() < OTP_RESEND_SECONDS:
        wait = OTP_RESEND_SECONDS - int((now - last).total_seconds())
        raise RateLimited(wait)
    code = await _issue_otp(deps, user.id, now)
    await deps.db.commit()
    await sms_sender(deps.settings, deps.redis).send(
        user.phone_e164, f"Your DevSync code is {code}"
    )


async def verify_phone_otp(deps: AuthDeps, principal: Principal, code: str, now: datetime) -> None:
    """Check the code (5-minute expiry, 5 attempts, constant-time). Commits."""
    user = await _load_self(deps, principal)
    if user.phone_verified_at is not None:
        raise DomainError(code=ErrorCode.ALREADY_VERIFIED)
    otp = await repo.latest_otp(deps.db, user.id, OtpPurpose.PHONE_VERIFY)
    if otp is None or otp.expires_at <= now or otp.attempts >= OTP_MAX_ATTEMPTS:
        raise DomainError(code=ErrorCode.TOKEN_INVALID)
    if not constant_time_equals(otp.code_hash, otp_hash(deps.settings, user.id, code)):
        otp.attempts += 1
        await deps.db.commit()
        raise DomainError(code=ErrorCode.TOKEN_INVALID)
    otp.consumed_at = now
    user.phone_verified_at = now
    await write_audit(
        deps.db, action="user.phone_verified", entity_type="user", entity_id=user.id,
        actor_id=user.id, actor_role=str(user.role),
    )  # fmt: skip
    await _activate_if_complete(deps, user, now)
    await deps.db.commit()


async def verify_email(deps: AuthDeps, token: str, now: datetime) -> None:
    """Consume an email link (public endpoint). Commits."""
    user_id = await repo.consume_email_token(
        deps.db, token_digest(token), EmailTokenPurpose.VERIFY, now
    )
    if user_id is None:
        raise DomainError(code=ErrorCode.TOKEN_INVALID)
    await act_as(deps.db, user_id, "SELF")
    user = await repo.get_user(deps.db, user_id)
    if user is None:
        raise DomainError(code=ErrorCode.TOKEN_INVALID)
    if user.email_verified_at is None:
        user.email_verified_at = now
        await write_audit(
            deps.db, action="user.email_verified", entity_type="user", entity_id=user.id,
            actor_id=user.id, actor_role=str(user.role),
        )  # fmt: skip
    await _activate_if_complete(deps, user, now)
    await deps.db.commit()


async def resend_verification_email(deps: AuthDeps, principal: Principal, now: datetime) -> None:
    """New verification link (old ones stop working). Commits."""
    user = await _load_self(deps, principal)
    if user.email_verified_at is not None:
        raise DomainError(code=ErrorCode.ALREADY_VERIFIED)
    await _issue_email_token(deps, user.id, user.display_name, str(user.email), now)
    await deps.db.commit()
