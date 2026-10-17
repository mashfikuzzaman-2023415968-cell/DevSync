"""Timed skill tests (spec §7.2, §17 Phase 3): start → answer before the deadline → submit.

The server clock decides everything: the deadline is set at start, late answers are refused,
and attempts left open past their deadline are scored as they stand (on the next read, or by
the `score_expired_attempts` job). One scored attempt per test every 30 days; no practice mode,
which protects the question bank. Scoring happens inside the database, so correct answers never
reach this process.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.authz import authorize
from app.core.errors import DomainError, ErrorCode, NotFoundError
from app.models.profiles import TestAttempt
from app.repositories import skill_tests as repo
from app.schemas.skill_tests import (
    AnswerAccepted,
    AnswerIn,
    AttemptOut,
    AttemptQuestion,
    AttemptResult,
    SkillTestOut,
)
from app.services.context import Ctx

RETAKE_AFTER = timedelta(days=30)
SEED_BITS = 62

# SQLSTATEs raised by the definer functions of migration 0004.
_NOT_FOUND = "P0002"  # no_data_found
_CONFLICT = "23505"  # unique_violation (attempt already open / already submitted)
_CHECK = "23514"  # check_violation (retake window, invalid answer)


def _sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _state_error(message: str, current: str, allowed: list[str], **extra: object) -> DomainError:
    return DomainError(
        message,
        code=ErrorCode.INVALID_STATE,
        extra={"current_state": current, "allowed_actions": allowed, **extra},
    )


def _is_open(a: TestAttempt, now: datetime) -> bool:
    return a.submitted_at is None and a.deadline_at > now


def next_attempt_at(attempts: Sequence[TestAttempt], now: datetime) -> datetime | None:
    """When the next scored attempt is allowed (None: now)."""
    scored = [a.started_at for a in attempts if a.scored]
    if not scored:
        return None
    allowed = max(scored) + RETAKE_AFTER
    return allowed if allowed > now else None


async def list_tests(ctx: Ctx) -> list[SkillTestOut]:
    tests = await repo.list_tests(ctx.db)
    attempts = await repo.attempts_of(ctx.db, ctx.uid)
    out = []
    for test, skill in tests:
        mine = [a for a in attempts if a.test_id == test.id]  # newest first
        done = [a for a in mine if a.submitted_at is not None and a.scored]
        open_attempt = next((a for a in mine if _is_open(a, ctx.now)), None)
        out.append(
            SkillTestOut(
                id=test.id,
                skill_id=skill.id,
                skill_name=skill.name,
                title=test.title,
                question_count=test.question_count,
                time_limit_seconds=test.time_limit_seconds,
                last_score=done[0].score if done else None,
                last_attempt_at=done[0].submitted_at if done else None,
                next_attempt_at=next_attempt_at(mine, ctx.now),
                open_attempt_id=open_attempt.id if open_attempt else None,
            )
        )
    return out


async def _view(ctx: Ctx, attempt: TestAttempt) -> AttemptOut:
    test = await repo.get_test(ctx.db, attempt.test_id)
    questions = await repo.attempt_questions(ctx.db, attempt.id)
    return AttemptOut(
        id=attempt.id,
        test_id=attempt.test_id,
        title=test.title if test else "",
        started_at=attempt.started_at,
        deadline_at=attempt.deadline_at,
        server_now=ctx.now,
        submitted_at=attempt.submitted_at,
        score=attempt.score,
        questions=[
            AttemptQuestion(id=q.id, ordinal=q.ordinal, text=q.text, options=q.options)
            for q in questions
        ],
        answers={str(k): int(v) for k, v in attempt.answers.items()},
    )


async def start_attempt(ctx: Ctx, test_id: uuid.UUID) -> AttemptOut:
    test = await repo.get_test(ctx.db, test_id)
    if test is None or not test.active:
        raise NotFoundError
    mine = [a for a in await repo.attempts_of(ctx.db, ctx.uid) if a.test_id == test_id]
    open_attempt = next((a for a in mine if _is_open(a, ctx.now)), None)
    if open_attempt is not None:
        raise _state_error(
            "You already have this test open.", "IN_PROGRESS", ["resume"],
            attempt_id=str(open_attempt.id),
        )  # fmt: skip
    allowed_at = next_attempt_at(mine, ctx.now)
    if allowed_at is not None:
        raise _state_error(
            "You can take this test again 30 days after your last attempt.",
            "RETAKE_LOCKED",
            [],
            next_attempt_at=allowed_at.isoformat(),
        )
    seed = secrets.randbits(SEED_BITS)
    try:
        attempt_id, _deadline = await repo.start_attempt(ctx.db, test_id, ctx.now, seed)
    except DBAPIError as exc:  # a parallel start won the race, or the bank is too small
        await ctx.db.rollback()
        state = _sqlstate(exc)
        if state in (_CONFLICT, _CHECK):
            raise _state_error("You can't start this test right now.", "LOCKED", []) from None
        if state == _NOT_FOUND:
            raise NotFoundError from None
        raise
    await write_audit(
        ctx.db,
        action="skill_test.start",
        entity_type="test_attempt",
        entity_id=attempt_id,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        after={"test_id": str(test_id)},
    )
    await ctx.db.commit()
    attempt = await repo.get_attempt(ctx.db, attempt_id)
    if attempt is None:  # pragma: no cover - just inserted by the caller
        raise NotFoundError
    return await _view(ctx, attempt)


async def _own_attempt(ctx: Ctx, attempt_id: uuid.UUID) -> TestAttempt:
    attempt = await repo.get_attempt(ctx.db, attempt_id)
    if attempt is None:
        raise NotFoundError
    authorize(ctx.principal, "test.take", attempt)  # someone else's attempt → 404
    return attempt


async def _score(ctx: Ctx, attempt: TestAttempt, *, audit_action: str) -> AttemptResult:
    try:
        score = await repo.score_attempt(ctx.db, attempt.id, ctx.now)
    except DBAPIError as exc:  # submitted by a parallel request a moment ago
        await ctx.db.rollback()
        if _sqlstate(exc) == _CONFLICT:
            raise _state_error("This test is already submitted.", "SUBMITTED", []) from None
        raise
    await write_audit(
        ctx.db,
        action=audit_action,
        entity_type="test_attempt",
        entity_id=attempt.id,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        after={"score": str(score.score)},
    )
    await ctx.db.commit()
    return AttemptResult(
        id=attempt.id,
        score=score.score,
        correct=score.correct,
        total=score.total,
        submitted_at=ctx.now,
        added_to_profile=attempt.scored,
    )


async def get_attempt(ctx: Ctx, attempt_id: uuid.UUID) -> AttemptOut:
    attempt = await _own_attempt(ctx, attempt_id)
    if attempt.submitted_at is None and attempt.deadline_at <= ctx.now:
        await _score(ctx, attempt, audit_action="skill_test.expire")  # time ran out
        attempt = await _own_attempt(ctx, attempt_id)
    return await _view(ctx, attempt)


async def answer(ctx: Ctx, attempt_id: uuid.UUID, body: AnswerIn) -> AnswerAccepted:
    attempt = await _own_attempt(ctx, attempt_id)
    if attempt.submitted_at is not None:
        raise _state_error("This test is already submitted.", "SUBMITTED", [])
    if ctx.now > attempt.deadline_at:
        raise _state_error("Time is up for this test.", "EXPIRED", ["submit"])
    try:
        accepted = await repo.record_answer(
            ctx.db, attempt.id, body.question_id, body.choice, ctx.now
        )
    except DBAPIError as exc:
        await ctx.db.rollback()
        if _sqlstate(exc) == _CHECK:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                fields={"question_id": "This question isn't part of the attempt."},
            ) from None
        raise
    if not accepted:  # the deadline passed or it was submitted in the meantime
        await ctx.db.rollback()
        raise _state_error("Time is up for this test.", "EXPIRED", ["submit"])
    await ctx.db.commit()
    refreshed = await _own_attempt(ctx, attempt_id)
    return AnswerAccepted(
        question_id=body.question_id, choice=body.choice, answered=len(refreshed.answers)
    )


async def submit(ctx: Ctx, attempt_id: uuid.UUID) -> AttemptResult:
    attempt = await _own_attempt(ctx, attempt_id)
    if attempt.submitted_at is not None:
        raise _state_error("This test is already submitted.", "SUBMITTED", [])
    return await _score(ctx, attempt, audit_action="skill_test.submit")


async def score_expired_attempts(db: AsyncSession, now: datetime, limit: int = 200) -> int:
    """Worker job (SYSTEM context): score attempts whose time ran out without a submit."""
    done = 0
    for attempt_id in await repo.expired_open_attempts(db, now, limit):
        try:
            await repo.score_attempt(db, attempt_id, now)
            await write_audit(
                db,
                action="skill_test.expire",
                entity_type="test_attempt",
                entity_id=attempt_id,
                actor_role="SYSTEM",
            )
            await db.commit()
            done += 1
        except DBAPIError as exc:  # submitted by its owner meanwhile
            await db.rollback()
            if _sqlstate(exc) != _CONFLICT:
                raise
    return done
