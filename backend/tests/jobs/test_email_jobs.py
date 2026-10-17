"""Outbox delivery and lifecycle cleanup jobs (spec §11, §15.6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import insert, select

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


async def test_expire_records_runs() -> None:
    counts = await email_jobs.expire_records()
    assert set(counts) == {"sessions", "email_tokens", "otp_codes", "idempotency_keys"}
