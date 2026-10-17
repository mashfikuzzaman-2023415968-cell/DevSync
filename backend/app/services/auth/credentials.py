"""Passwords, admin TOTP, recovery codes and step-up (spec §14.4).

- Forgot password always answers the same way; reset links last 30 minutes,
  work once, and resetting signs the user out everywhere.
- TOTP secrets are AES-GCM encrypted (associated data = user id, so a secret
  copied to another user's row cannot be decrypted).
- Step-up = a fresh TOTP within the last 10 minutes, required for sensitive
  admin actions; it rotates the session token.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pyotp

from app.core.audit import write_audit
from app.core.authz import Principal
from app.core.errors import AuthError, DomainError, ErrorCode
from app.core.security import (
    DecryptionError,
    decrypt,
    encrypt,
    generate_recovery_codes,
    generate_token,
    hash_password,
    token_digest,
    verify_password,
)
from app.core.sessions import SessionData, SessionPolicy, SessionStore
from app.models.identity import EmailTokenPurpose, TotpCredential, UserStatus
from app.repositories import users as repo
from app.services import outbox
from app.services.auth.common import (
    RESET_TOKEN_TTL,
    STEP_UP_TTL,
    TOTP_ISSUER,
    AuthDeps,
    act_as,
    reset_link,
    totp_key,
)
from app.services.auth.login import check_second_factor, verify_totp_code
from app.services.auth.registration import reject_weak_password

UNIFORM_FORGOT_MESSAGE = "If an account exists for that email, we've sent a reset link."


async def forgot_password(deps: AuthDeps, email: str, now: datetime) -> None:
    """Email a reset link if the account exists; same answer either way. Commits."""
    found = await repo.user_by_email(deps.db, email)
    if found is not None and found[1] in (UserStatus.ACTIVE.value, UserStatus.PENDING.value):
        user_id, _status, name = found
        await act_as(deps.db, user_id, "SELF")
        await repo.invalidate_email_tokens(deps.db, user_id, EmailTokenPurpose.RESET, now)
        token = generate_token(32)
        await repo.add_email_token(
            deps.db, user_id, EmailTokenPurpose.RESET, token_digest(token), now + RESET_TOKEN_TTL
        )
        await outbox.enqueue(
            deps.db,
            to=email,
            template="reset_password",
            payload={"name": name, "link": reset_link(deps.settings, token)},
        )
        await write_audit(
            deps.db, action="auth.reset_requested", entity_type="user", entity_id=user_id
        )
    await deps.db.commit()


async def reset_password(deps: AuthDeps, token: str, new_password: str, now: datetime) -> None:
    """Set a new password from a reset link; revokes every session. Commits."""
    user_id = await repo.consume_email_token(
        deps.db, token_digest(token), EmailTokenPurpose.RESET, now
    )
    if user_id is None:
        raise DomainError(code=ErrorCode.TOKEN_INVALID)
    await act_as(deps.db, user_id, "SELF")
    user = await repo.get_user(deps.db, user_id)
    if user is None:
        raise DomainError(code=ErrorCode.TOKEN_INVALID)
    reject_weak_password(new_password, [str(user.email), user.display_name])
    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    store = SessionStore(deps.redis, SessionPolicy(deps.settings))
    revoked = await store.revoke_all(deps.db, user_id, now)
    await write_audit(
        deps.db,
        action="auth.password_reset",
        entity_type="user",
        entity_id=user_id,
        actor_id=user_id,
        actor_role=str(user.role),
        after={"sessions_revoked": revoked},
    )
    await outbox.enqueue(deps.db, to=str(user.email), template="password_changed", payload={
        "name": user.display_name, "link": f"{deps.settings.PUBLIC_ORIGIN}/forgot-password",
    })  # fmt: skip
    await deps.db.commit()


async def change_password(
    deps: AuthDeps,
    principal: Principal,
    session: tuple[str, SessionData],
    *,
    current_password: str,
    new_password: str,
    now: datetime,
) -> tuple[str, SessionData]:
    """Change password; other sessions are revoked and this one is rotated. Commits."""
    user = await repo.get_user(deps.db, principal.user_id)
    if user is None or not verify_password(user.password_hash, current_password).ok:
        raise AuthError(code=ErrorCode.INVALID_CREDENTIALS)
    reject_weak_password(new_password, [str(user.email), user.display_name])
    user.password_hash = hash_password(new_password)
    store = SessionStore(deps.redis, SessionPolicy(deps.settings))
    token, data = session
    revoked = await store.revoke_all(deps.db, user.id, now, except_id=data.session_id)
    new_token, new_data = await store.rotate(deps.db, token, data, now)
    await write_audit(
        deps.db,
        action="auth.password_changed",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        actor_role=principal.role,
        after={"sessions_revoked": revoked},
    )
    await outbox.enqueue(deps.db, to=str(user.email), template="password_changed", payload={
        "name": user.display_name, "link": f"{deps.settings.PUBLIC_ORIGIN}/forgot-password",
    })  # fmt: skip
    await deps.db.commit()
    return new_token, new_data


def _encrypt_secret(deps: AuthDeps, user_id: uuid.UUID, secret: str) -> bytes:
    return encrypt(totp_key(deps.settings), secret.encode(), str(user_id).encode())


async def totp_setup(deps: AuthDeps, principal: Principal, now: datetime) -> tuple[str, str]:
    """Create (or replace an unconfirmed) TOTP secret. Re-setup of a confirmed one needs
    step-up. Returns (provisioning URI, secret). Commits."""
    user = await repo.get_user(deps.db, principal.user_id)
    if user is None:
        raise AuthError
    credential = await repo.totp_credential(deps.db, user.id)
    if (
        credential is not None
        and credential.confirmed_at is not None
        and not principal.has_step_up(now)
    ):
        raise DomainError(code=ErrorCode.STEP_UP_REQUIRED)
    secret = pyotp.random_base32()
    encrypted = _encrypt_secret(deps, user.id, secret)
    if credential is None:
        deps.db.add(TotpCredential(user_id=user.id, secret_encrypted=encrypted))
    else:
        credential.secret_encrypted = encrypted
        credential.confirmed_at = None
        credential.last_used_step = None
    await write_audit(
        deps.db,
        action="auth.totp_setup_started",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        actor_role=principal.role,
    )
    await deps.db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=str(user.email), issuer_name=TOTP_ISSUER)
    return uri, secret


async def totp_confirm(
    deps: AuthDeps,
    principal: Principal,
    session: tuple[str, SessionData],
    code: str,
    now: datetime,
) -> tuple[list[str], str, SessionData]:
    """Confirm the pending secret with a code; returns recovery codes (shown once) and the
    rotated, TOTP-verified session. Commits."""
    credential = await repo.totp_credential(deps.db, principal.user_id)
    if credential is None or credential.confirmed_at is not None:
        raise DomainError("Start TOTP setup first.", code=ErrorCode.INVALID_STATE)
    try:
        secret = decrypt(
            totp_key(deps.settings), credential.secret_encrypted, str(principal.user_id).encode()
        ).decode()
    except DecryptionError as exc:
        raise DomainError(code=ErrorCode.TOKEN_INVALID) from exc
    step = verify_totp_code(secret, code, now, None)
    if step is None:
        raise DomainError(code=ErrorCode.TOKEN_INVALID)
    credential.confirmed_at = now
    credential.last_used_step = step
    codes = generate_recovery_codes()
    await repo.replace_recovery_codes(
        deps.db, principal.user_id, [hash_password(c) for c in codes], now
    )
    store = SessionStore(deps.redis, SessionPolicy(deps.settings))
    token, data = session
    new_token, new_data = await store.rotate(deps.db, token, data, now, totp_verified=True)
    await write_audit(
        deps.db,
        action="auth.totp_enabled",
        entity_type="user",
        entity_id=principal.user_id,
        actor_id=principal.user_id,
        actor_role=principal.role,
    )
    await deps.db.commit()
    return codes, new_token, new_data


async def regenerate_recovery_codes(
    deps: AuthDeps, principal: Principal, now: datetime
) -> list[str]:
    """New recovery codes (old ones stop working); requires step-up. Commits."""
    if not principal.has_step_up(now):
        raise DomainError(code=ErrorCode.STEP_UP_REQUIRED)
    codes = generate_recovery_codes()
    await repo.replace_recovery_codes(
        deps.db, principal.user_id, [hash_password(c) for c in codes], now
    )
    await write_audit(
        deps.db,
        action="auth.recovery_codes_regenerated",
        entity_type="user",
        entity_id=principal.user_id,
        actor_id=principal.user_id,
        actor_role=principal.role,
    )
    await deps.db.commit()
    return codes


async def step_up(
    deps: AuthDeps,
    principal: Principal,
    session: tuple[str, SessionData],
    code: str,
    now: datetime,
) -> tuple[str, SessionData]:
    """Re-check TOTP; sensitive admin actions are allowed for 10 minutes. Commits."""
    if not await check_second_factor(deps, principal.user_id, code, None, now):
        await write_audit(
            deps.db,
            action="auth.step_up_failed",
            entity_type="user",
            entity_id=principal.user_id,
            actor_id=principal.user_id,
            actor_role=principal.role,
        )
        await deps.db.commit()
        raise AuthError(code=ErrorCode.TOTP_REQUIRED)
    store = SessionStore(deps.redis, SessionPolicy(deps.settings))
    token, data = session
    new_token, new_data = await store.rotate(
        deps.db, token, data, now, step_up_until=now + STEP_UP_TTL, totp_verified=True
    )
    await write_audit(
        deps.db,
        action="auth.step_up",
        entity_type="session",
        entity_id=data.session_id,
        actor_id=principal.user_id,
        actor_role=principal.role,
    )
    await deps.db.commit()
    return new_token, new_data
