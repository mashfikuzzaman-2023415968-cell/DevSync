"""Outbox delivery and lifecycle cleanup jobs (spec §11, §15.6)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import insert, select, update

from app.db.context import DbContext
from app.db.session import open_session
from app.jobs import email_jobs
from app.models.identity import EmailOutbox, OutboxStatus
from tests.helpers import stack_available, unique_email

pytestmark = pytest.mark.jobs


@pytest.fixture(autouse=True)
def _stack(migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")


@pytest.fixture(autouse=True)
async def _empty_queue(_stack: None) -> None:
    """Start each test with no email waiting: earlier suites (sign-ups in E2E runs) leave
    hundreds queued, and a batch takes the oldest first, so a test's own email might not run."""
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(
            update(EmailOutbox)
            .where(EmailOutbox.status == OutboxStatus.PENDING)
            .values(status=OutboxStatus.FAILED, last_error="cleared by test")
        )
        await db.commit()


async def _enqueue(to: str) -> None:
    async with open_session(DbContext.guest()) as db:
        await db.execute(
            insert(EmailOutbox).values(
                to_email=to,
                template="verify_email",
                payload={"name": "N", "link": "https://x/verify-email?token=secret"},
            )
        )
        await db.commit()


async def _row(to: str) -> dict[str, Any]:
    """Snapshot of the outbox row (plain values, safe to use after the session closes)."""
    async with open_session(DbContext.system(), job=True) as db:
        row = (await db.execute(select(EmailOutbox).where(EmailOutbox.to_email == to))).scalar_one()
        return {
            "status": row.status,
            "attempts": row.attempts,
            "last_error": row.last_error,
            "next_attempt_at": row.next_attempt_at,
            "payload": dict(row.payload),
        }


async def test_successful_send_marks_sent_and_scrubs_link(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[Any] = []
    monkeypatch.setattr(email_jobs, "send_via_smtp", lambda _s, m: sent.append(m))
    to = unique_email()
    await _enqueue(to)
    counts = await email_jobs.send_due_emails()
    assert counts["sent"] >= 1
    row = await _row(to)
    assert row["status"] == OutboxStatus.SENT
    assert row["payload"]["link"] == "[sent]"
    assert any(m["To"] == to for m in sent)


async def test_failures_back_off_then_give_up(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_s: Any, _m: Any) -> None:
        raise ConnectionError("smtp down")

    monkeypatch.setattr(email_jobs, "send_via_smtp", boom)
    to = unique_email()
    await _enqueue(to)
    await email_jobs.send_due_emails()
    row = await _row(to)
    assert (row["status"], row["attempts"], row["last_error"]) == (
        OutboxStatus.PENDING,
        1,
        "ConnectionError",
    )
    assert row["next_attempt_at"] > datetime.now(UTC)
    # Force it due repeatedly until it gives up after 5 attempts.
    for _ in range(4):
        async with open_session(DbContext.system(), job=True) as db:
            r = (
                await db.execute(select(EmailOutbox).where(EmailOutbox.to_email == to))
            ).scalar_one()
            r.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()
        await email_jobs.send_due_emails()
    assert (await _row(to))["status"] == OutboxStatus.FAILED


async def test_no_transaction_is_held_open_while_smtp_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A slow SMTP server used to outlast the worker's idle-in-transaction timeout, losing the
    # batch's results so the same emails went out again on every run.
    to = unique_email()
    seen_during_send: list[dict[str, Any]] = []

    def slow_send(_s: Any, message: Any) -> None:
        if message["To"] == to:
            # Another connection already sees the claim: it was committed before sending.
            seen_during_send.append(asyncio.run(_row(to)))

    monkeypatch.setattr(email_jobs, "send_via_smtp", slow_send)
    await _enqueue(to)
    await email_jobs.send_due_emails()
    assert seen_during_send
    claim = seen_during_send[0]
    assert claim["attempts"] == 1
    assert claim["status"] == OutboxStatus.PENDING
    assert claim["next_attempt_at"] > datetime.now(UTC)  # leased, so no other run takes it
    done = await _row(to)
    assert done["status"] == OutboxStatus.SENT
    assert done["attempts"] == 1


async def test_expire_records_runs() -> None:
    counts = await email_jobs.expire_records()
    assert set(counts) == {"sessions", "email_tokens", "otp_codes", "idempotency_keys"}
