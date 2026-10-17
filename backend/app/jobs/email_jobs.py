"""`email.send` (every 30 s) and `lifecycle.expire` cleanup (spec §11).

Email delivery reads due outbox rows with `FOR UPDATE SKIP LOCKED` (so several
workers never send the same email), sends via SMTP, and marks them SENT. Failures
are retried up to 5 times with exponential backoff, then marked FAILED. After a
successful send the payload's link is scrubbed, so database readers can't reuse
verification or reset links.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, update

from app.core.clock import get_clock
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.context import DbContext
from app.db.session import open_session
from app.integrations.email import build_message, send_via_smtp
from app.models.foundation import IdempotencyKey
from app.models.identity import EmailOutbox, EmailToken, OtpCode, OutboxStatus, Session

log = get_logger(__name__)
BATCH_SIZE = 20
MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 30
SESSION_RETENTION = timedelta(days=30)
OTP_RETENTION = timedelta(days=1)


def backoff(attempts: int) -> timedelta:
    """30 s, 60 s, 120 s, 240 s… after each failed attempt."""
    return timedelta(seconds=BASE_BACKOFF_SECONDS * 2 ** max(0, attempts - 1))


async def send_due_emails() -> dict[str, int]:
    """Send up to one batch of due emails; returns counts by outcome."""
    settings = get_settings()
    now = get_clock().now()
    counts = {"sent": 0, "retry": 0, "failed": 0}
    async with open_session(DbContext.system(), job=True) as db:
        rows = (
            (
                await db.execute(
                    select(EmailOutbox)
                    .where(
                        EmailOutbox.status == OutboxStatus.PENDING,
                        EmailOutbox.next_attempt_at <= now,
                    )
                    .order_by(EmailOutbox.next_attempt_at)
                    .limit(BATCH_SIZE)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            try:
                message = build_message(settings, row.to_email, row.template, row.payload)
                await asyncio.to_thread(send_via_smtp, settings, message)
            except Exception as exc:  # any send error: retry with backoff, then give up
                row.attempts += 1
                row.last_error = type(exc).__name__
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = OutboxStatus.FAILED
                    counts["failed"] += 1
                else:
                    row.next_attempt_at = now + backoff(row.attempts)
                    counts["retry"] += 1
                log.warning("email_send_failed", template=row.template, attempts=row.attempts)
                continue
            row.status = OutboxStatus.SENT
            row.attempts += 1
            row.payload = _scrubbed(row.payload)
            counts["sent"] += 1
        await db.commit()
    return counts


def _scrubbed(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: ("[sent]" if k == "link" else v) for k, v in payload.items()}


async def expire_records() -> dict[str, int]:
    """Delete old sessions (30 days after expiry), expired tokens, OTPs and idempotency keys."""
    now = get_clock().now()
    async with open_session(DbContext.system(), job=True) as db:
        sessions = await db.execute(
            delete(Session).where(Session.expires_at < now - SESSION_RETENTION)
        )
        tokens = await db.execute(delete(EmailToken).where(EmailToken.expires_at < now))
        otps = await db.execute(delete(OtpCode).where(OtpCode.expires_at < now - OTP_RETENTION))
        keys = await db.execute(delete(IdempotencyKey).where(IdempotencyKey.expires_at < now))
        await db.execute(
            update(Session)
            .where(Session.revoked_at.is_(None), Session.expires_at < now)
            .values(revoked_at=now)
        )
        await db.commit()
    return {
        "sessions": int(sessions.rowcount or 0),  # type: ignore[attr-defined]
        "email_tokens": int(tokens.rowcount or 0),  # type: ignore[attr-defined]
        "otp_codes": int(otps.rowcount or 0),  # type: ignore[attr-defined]
        "idempotency_keys": int(keys.rowcount or 0),  # type: ignore[attr-defined]
    }


def email_send() -> dict[str, int]:
    """RQ entry point (sync wrapper)."""
    return asyncio.run(send_due_emails())


def lifecycle_expire() -> dict[str, int]:
    """RQ entry point (sync wrapper)."""
    return asyncio.run(expire_records())
