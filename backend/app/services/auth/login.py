"""Sign-in: password, lockout, adaptive CAPTCHA, admin TOTP (spec §14.4, §14.16).

Abuse controls, in order:
1. per IP+email rate limit (5/min, 20/hour) and a progressive delay after 5
   failures (429 with a growing `Retry-After`);
2. CAPTCHA required after 3 recent failures for the account or the IP, and
   always for admins;
3. account lock for 15 minutes after 10 failures within an hour (+ email notice);
4. uniform "Email or password is incorrect" and constant-ish timing (a dummy
   Argon2 hash is checked when the account doesn't exist).

Admins never get a full session from the password alone: they receive a
short-lived pre-auth token and must pass TOTP (or a recovery code).
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

import pyotp

from app.core import captcha
from app.core.audit import write_audit
from app.core.errors import AuthError, DomainError, ErrorCode
from app.core.ratelimit import RateLimited, RateLimiter, Rule, hash_key
from app.core.redirects import safe_redirect
from app.core.security import (
    DecryptionError,
    decrypt,
    hash_password,
    normalize_recovery_code,
    verify_password,
)
from app.core.sessions import SessionData, SessionPolicy, SessionStore
from app.core.settings_cache import active_settings
from app.models.identity import UserStatus
from app.repositories import users as repo
from app.schemas.platform_settings import RateLimitSettings
from app.services import outbox
from app.services.auth.common import (
    PRE_AUTH_TTL_SECONDS,
    TOTP_INTERVAL,
    AuthDeps,
    act_as,
    device_fingerprint,
    totp_key,
)

FAILURE_WINDOW_SECONDS = 3600
FAIL_KEY = "auth:fail:"
DELAY_KEY = "auth:delay:"
PRE_AUTH_KEY = "auth:preauth:"
MAX_PROGRESSIVE_DELAY = 60


@dataclass(frozen=True)
class SignedIn:
    """A new session to put in the cookie."""

    token: str
    data: SessionData
    redirect_to: str


@dataclass(frozen=True)
class TotpChallenge:
    """Admin passed the password step; TOTP still required."""

    pre_auth: str


@dataclass(frozen=True)
class ClientInfo:
    """Where the request came from (for sessions, fingerprints, limits)."""

    ip: str
    user_agent: str | None


async def _failures(deps: AuthDeps, *keys: str) -> int:
    counts = [int(await deps.redis.get(FAIL_KEY + k) or 0) for k in keys]
    return max(counts, default=0)


async def _count_failure(deps: AuthDeps, *keys: str) -> int:
    worst = 0
    for k in keys:
        n = int(await deps.redis.incr(FAIL_KEY + k))
        if n == 1:
            await deps.redis.expire(FAIL_KEY + k, FAILURE_WINDOW_SECONDS)
        worst = max(worst, n)
    return worst


async def login(
    deps: AuthDeps,
    now: datetime,
    client: ClientInfo,
    *,
    email: str,
    password: str,
    captcha_payload: str | None,
    honeypot: str | None,
    started_at_ms: int | None,
    return_to: str | None,
) -> SignedIn | TotpChallenge:
    """Check credentials and start a session (or the admin TOTP step). Commits."""
    db = deps.db
    limits = (await active_settings(db)).ratelimit
    email_key = hash_key(email)
    ip_key = hash_key(client.ip)
    limiter = RateLimiter(deps.redis)
    await limiter.hit(
        "login", hash_key(client.ip, email), [Rule(r.limit, r.window_seconds) for r in limits.login]
    )

    delay = await deps.redis.ttl(DELAY_KEY + email_key)
    if delay and delay > 0:
        raise RateLimited(int(delay))

    captcha_needed = await _failures(deps, email_key, ip_key) >= limits.login_captcha_after_failures
    if captcha_needed or honeypot:
        await _check_captcha(deps, captcha_payload, honeypot, started_at_ms)

    record = await repo.login_lookup(db, email)
    check = verify_password(record.password_hash if record else None, password)

    if record is not None and record.locked_until is not None and record.locked_until > now:
        minutes = max(1, int((record.locked_until - now).total_seconds() // 60) + 1)
        raise DomainError(
            f"Too many failed attempts. Try again in {minutes} minutes.",
            code=ErrorCode.ACCOUNT_LOCKED,
            extra={"locked_minutes": minutes},
        )

    if record is None or not check.ok:
        await _handle_failure(
            deps, now, record=record, email=email, email_key=email_key, ip_key=ip_key, limits=limits
        )
        raise AuthError(code=ErrorCode.INVALID_CREDENTIALS)

    if record.status in (UserStatus.SUSPENDED.value, UserStatus.DELETED.value):
        raise AuthError(
            "This account is suspended. Contact support.", code=ErrorCode.UNAUTHENTICATED
        )

    if record.role == "ADMIN" and not captcha_needed:
        # Admin sign-in always requires the CAPTCHA (spec §14.16).
        await _check_captcha(deps, captcha_payload, honeypot, started_at_ms)

    await limiter.reset(
        "login", hash_key(client.ip, email), [Rule(r.limit, r.window_seconds) for r in limits.login]
    )
    await deps.redis.delete(FAIL_KEY + email_key, DELAY_KEY + email_key)

    await act_as(db, record.id, record.role)
    user = await repo.get_user(db, record.id)
    if user is None:
        raise AuthError(code=ErrorCode.INVALID_CREDENTIALS)
    user.failed_login_count = 0
    user.first_failed_login_at = None
    user.locked_until = None
    if check.needs_rehash:
        user.password_hash = hash_password(password)

    if record.role == "ADMIN":
        credential = await repo.totp_credential(db, record.id)
        if credential is not None and credential.confirmed_at is not None:
            pre_auth = secrets.token_urlsafe(32)
            await deps.redis.set(
                PRE_AUTH_KEY + pre_auth,
                json.dumps({"user_id": str(record.id), "return_to": return_to}),
                ex=PRE_AUTH_TTL_SECONDS,
            )
            await write_audit(
                db,
                action="auth.password_ok_totp_pending",
                entity_type="user",
                entity_id=record.id,
                actor_id=record.id,
                actor_role="ADMIN",
                ip=client.ip,
            )
            await db.commit()
            return TotpChallenge(pre_auth=pre_auth)
        # No TOTP yet: a session limited to setting it up (admin powers need totp_verified).
        return await _start_session(
            deps,
            now,
            client,
            user_id=user.id,
            role="ADMIN",
            status=str(user.status),
            email=str(user.email),
            display_name=user.display_name,
            redirect_to="/admin/setup-2fa",
            totp_verified=False,
        )

    target = safe_redirect(return_to, record.role, str(user.status))
    return await _start_session(
        deps,
        now,
        client,
        user_id=user.id,
        role=record.role,
        status=str(user.status),
        email=str(user.email),
        display_name=user.display_name,
        redirect_to=target,
        totp_verified=False,
    )


async def _check_captcha(
    deps: AuthDeps, payload: str | None, honeypot: str | None, started_at_ms: int | None
) -> None:
    try:
        await captcha.verify(
            deps.redis,
            deps.settings.CAPTCHA_HMAC_KEY,
            payload=payload,
            honeypot=honeypot,
            started_at_ms=started_at_ms,
            bypass=deps.test_mode and payload == "test-bypass",
        )
    except captcha.CaptchaError as exc:
        raise captcha.CaptchaError(extra={"captcha_required": True}) from exc


async def _handle_failure(
    deps: AuthDeps,
    now: datetime,
    *,
    record: repo.LoginRecord | None,
    email: str,
    email_key: str,
    ip_key: str,
    limits: RateLimitSettings,
) -> None:
    lim = limits
    failures = await _count_failure(deps, email_key, ip_key)
    progressive_after = lim.login_progressive_after_failures
    if failures >= progressive_after:
        delay = min(2 ** (failures - progressive_after), MAX_PROGRESSIVE_DELAY)
        await deps.redis.set(DELAY_KEY + email_key, b"1", ex=delay)
    if record is None:
        await write_audit(deps.db, action="auth.login_failed", entity_type="user", entity_id=None)
        await deps.db.commit()
        return
    count, locked_until = await repo.record_login_failure(
        deps.db,
        record.id,
        now,
        window_seconds=FAILURE_WINDOW_SECONDS,
        lock_after=lim.login_lock_after_failures,
        lock_minutes=lim.login_lock_minutes,
    )
    await write_audit(
        deps.db,
        action="auth.login_failed",
        entity_type="user",
        entity_id=record.id,
        after={"failures_in_window": count},
    )
    newly_locked = (
        locked_until is not None
        and locked_until > now
        and (record.locked_until is None or record.locked_until <= now)
    )
    if newly_locked:
        existing = await repo.user_by_email(deps.db, email)
        name = existing[2] if existing else ""
        await outbox.enqueue(deps.db, to=email, template="account_locked", payload={
            "name": name, "minutes": lim.login_lock_minutes,
            "link": f"{deps.settings.PUBLIC_ORIGIN}/forgot-password",
        })  # fmt: skip
        await write_audit(
            deps.db, action="auth.account_locked", entity_type="user", entity_id=record.id
        )
    await deps.db.commit()


async def _start_session(
    deps: AuthDeps,
    now: datetime,
    client: ClientInfo,
    *,
    user_id: uuid.UUID,
    role: str,
    status: str,
    email: str,
    display_name: str,
    redirect_to: str,
    totp_verified: bool,
) -> SignedIn:
    db = deps.db
    user = await repo.get_user(db, user_id)
    if user is not None:
        user.last_login_at = now
    store = SessionStore(deps.redis, SessionPolicy(deps.settings))
    token, data = await store.create(
        db, user_id=user_id, role=role, status=status, now=now,
        ip=client.ip, user_agent=client.user_agent, totp_verified=totp_verified,
    )  # fmt: skip
    new_device = await repo.remember_device(
        db, user_id, device_fingerprint(client.user_agent, client.ip), now
    )
    if new_device:
        await outbox.enqueue(db, to=email, template="new_device", payload={
            "name": display_name, "device": (client.user_agent or "unknown browser")[:80],
            "link": f"{deps.settings.PUBLIC_ORIGIN}/settings",
        })  # fmt: skip
    await write_audit(
        db,
        action="auth.login",
        entity_type="session",
        entity_id=data.session_id,
        actor_id=user_id,
        actor_role=role,
        ip=client.ip,
        after={"totp_verified": totp_verified, "new_device": new_device},
    )
    await db.commit()
    return SignedIn(token=token, data=data, redirect_to=redirect_to)


def verify_totp_code(
    secret: str, code: str, now: datetime, last_used_step: int | None
) -> int | None:
    """Matching time step (window ±1) not used before, or None (replay-safe, §14.4)."""
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL)
    current = int(now.timestamp()) // TOTP_INTERVAL
    for step in (current - 1, current, current + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if secrets.compare_digest(totp.generate_otp(step), code):
            return step
    return None


async def login_totp(
    deps: AuthDeps,
    now: datetime,
    client: ClientInfo,
    *,
    pre_auth: str,
    code: str | None,
    recovery_code: str | None,
    return_to: str | None,
) -> SignedIn:
    """Second factor for admins. Commits."""
    raw = await deps.redis.get(PRE_AUTH_KEY + pre_auth)
    if raw is None or (code is None) == (recovery_code is None):
        raise AuthError(code=ErrorCode.TOTP_REQUIRED)
    info = json.loads(raw)
    user_id = uuid.UUID(info["user_id"])
    limits = (await active_settings(deps.db)).ratelimit
    await RateLimiter(deps.redis).hit(
        "totp", hash_key(str(user_id)), [Rule(r.limit, r.window_seconds) for r in limits.totp]
    )
    await act_as(deps.db, user_id, "ADMIN")
    if not await check_second_factor(deps, user_id, code, recovery_code, now):
        await write_audit(deps.db, action="auth.totp_failed", entity_type="user", entity_id=user_id)
        await deps.db.commit()
        raise AuthError(code=ErrorCode.TOTP_REQUIRED)
    await deps.redis.delete(PRE_AUTH_KEY + pre_auth)
    user = await repo.get_user(deps.db, user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthError(code=ErrorCode.INVALID_CREDENTIALS)
    target = safe_redirect(return_to or info.get("return_to"), "ADMIN", "ACTIVE")
    return await _start_session(
        deps,
        now,
        client,
        user_id=user_id,
        role="ADMIN",
        status="ACTIVE",
        email=str(user.email),
        display_name=user.display_name,
        redirect_to=target,
        totp_verified=True,
    )


async def check_second_factor(
    deps: AuthDeps, user_id: uuid.UUID, code: str | None, recovery_code: str | None, now: datetime
) -> bool:
    """TOTP code (records the step) or an unused recovery code (marks it used)."""
    if code is not None:
        credential = await repo.totp_credential(deps.db, user_id)
        if credential is None or credential.confirmed_at is None:
            return False
        try:
            secret = decrypt(
                totp_key(deps.settings), credential.secret_encrypted, str(user_id).encode()
            )
        except DecryptionError:
            return False
        step = verify_totp_code(secret.decode(), code, now, credential.last_used_step)
        if step is None:
            return False
        credential.last_used_step = step
        return True
    if recovery_code is not None:
        normalized = normalize_recovery_code(recovery_code)
        for row in await repo.unused_recovery_codes(deps.db, user_id):
            if verify_password(row.code_hash, normalized).ok:
                row.used_at = now
                await write_audit(
                    deps.db,
                    action="auth.recovery_code_used",
                    entity_type="user",
                    entity_id=user_id,
                    actor_id=user_id,
                    actor_role="ADMIN",
                )
                return True
    return False
