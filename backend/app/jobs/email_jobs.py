"""`email.send` (every 30 s) and `lifecycle.expire` cleanup (spec §11).

Email delivery claims due outbox rows with `FOR UPDATE SKIP LOCKED` and commits the claim (so
several workers never send the same email), sends via SMTP outside any transaction, and marks
each one SENT on its own. Failures
are retried up to 5 times with exponential backoff, then marked FAILED. After a
successful send the payload's link is scrubbed, so database readers can't reuse
verification or reset links.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update

from app.core.clock import get_clock
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.context import DbContext
from app.db.session import open_session
from app.integrations.email import build_message, send_via_smtp
from app.jobs.runs import prune_runs, run_recorded
from app.models.foundation import IdempotencyKey
from app.models.identity import EmailOutbox, EmailToken, OtpCode, OutboxStatus, Session

log = get_logger(__name__)
BATCH_SIZE = 20
MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 30
# How long a claimed email stays out of other runs; if the worker dies mid-send it is retried
# after this (at-least-once delivery, like any outbox).
CLAIM_LEASE = timedelta(minutes=5)
SESSION_RETENTION = timedelta(days=30)
OTP_RETENTION = timedelta(days=1)


def backoff(attempts: int) -> timedelta:
    """30 s, 60 s, 120 s, 240 s… after each failed attempt."""
    return timedelta(seconds=BASE_BACKOFF_SECONDS * 2 ** max(0, attempts - 1))


@dataclass(frozen=True)
class _Claimed:
    id: uuid.UUID
    to_email: str
    template: str
    payload: dict[str, Any]
    attempts: int


async def _claim(now: datetime) -> list[_Claimed]:
    """Take a batch of due emails and commit straight away: each is leased for a while (so no
    other run picks it up) and its attempt is counted, before any slow SMTP work starts."""
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
        claimed = []
        for row in rows:
            row.attempts += 1
            row.next_attempt_at = now + CLAIM_LEASE
            claimed.append(
                _Claimed(row.id, row.to_email, row.template, dict(row.payload), row.attempts)
            )
        await db.commit()
    return claimed


async def _record(email_id: uuid.UUID, **values: Any) -> None:
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(update(EmailOutbox).where(EmailOutbox.id == email_id).values(**values))
        await db.commit()


async def send_due_emails() -> dict[str, int]:
    """Send up to one batch of due emails; returns counts by outcome.

    No database transaction stays open while SMTP runs (a slow server used to outlast the
    worker's idle-in-transaction timeout, so the batch's results were lost and the same emails
    were sent again every run). Each result is recorded on its own as soon as it is known."""
    settings = get_settings()
    now = get_clock().now()
    counts = {"sent": 0, "retry": 0, "failed": 0}
    for email in await _claim(now):
        try:
            message = build_message(settings, email.to_email, email.template, email.payload)
            await asyncio.to_thread(send_via_smtp, settings, message)
        except Exception as exc:  # any send error: retry with backoff, then give up
            if email.attempts >= MAX_ATTEMPTS:
                await _record(email.id, status=OutboxStatus.FAILED, last_error=type(exc).__name__)
                counts["failed"] += 1
            else:
                await _record(
                    email.id,
                    next_attempt_at=get_clock().now() + backoff(email.attempts),
                    last_error=type(exc).__name__,
                )
                counts["retry"] += 1
            log.warning("email_send_failed", template=email.template, attempts=email.attempts)
            continue
        await _record(email.id, status=OutboxStatus.SENT, payload=_scrubbed(email.payload))
        counts["sent"] += 1
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
    counts = {
        "sessions": int(sessions.rowcount or 0),  # type: ignore[attr-defined]
        "email_tokens": int(tokens.rowcount or 0),  # type: ignore[attr-defined]
        "otp_codes": int(otps.rowcount or 0),  # type: ignore[attr-defined]
        "idempotency_keys": int(keys.rowcount or 0),  # type: ignore[attr-defined]
    }
    # Old job run records go with the rest of the expired rows (§11 maintenance).
    counts.update(await prune_runs(now))
    return counts


def email_send() -> dict[str, int]:
    """RQ entry point (sync wrapper); the run is recorded in `jobs` (§11)."""
    return asyncio.run(run_recorded("email.send", send_due_emails))


def lifecycle_expire() -> dict[str, int]:
    """RQ entry point (sync wrapper); the run is recorded in `jobs` (§11)."""
    return asyncio.run(run_recorded("lifecycle.expire", expire_records))
