"""Skill test queries. Attempts are written only through the SECURITY DEFINER functions of
migration 0004 (`start_test_attempt`, `record_test_answer`, `score_test_attempt`); questions are
read through `attempt_questions`, which never returns the correct answer."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import column, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profiles import Skill, SkillTest, TestAttempt


async def list_tests(db: AsyncSession) -> list[tuple[SkillTest, Skill]]:
    stmt = (
        select(SkillTest, Skill)
        .join(Skill, Skill.id == SkillTest.skill_id)
        .where(SkillTest.active.is_(True), Skill.active.is_(True))
        .order_by(Skill.name)
    )
    return [(t, s) for t, s in (await db.execute(stmt)).all()]


async def get_test(db: AsyncSession, test_id: uuid.UUID) -> SkillTest | None:
    return await db.scalar(select(SkillTest).where(SkillTest.id == test_id))


async def attempts_of(db: AsyncSession, user_id: uuid.UUID) -> Sequence[TestAttempt]:
    stmt = (
        select(TestAttempt)
        .where(TestAttempt.user_id == user_id)
        .order_by(TestAttempt.started_at.desc())
    )
    return (await db.scalars(stmt)).all()


async def get_attempt(db: AsyncSession, attempt_id: uuid.UUID) -> TestAttempt | None:
    """The attempt if the caller may read it (row-level security: owner or admin). Always
    re-read: the definer functions change the row behind the ORM's back."""
    stmt = (
        select(TestAttempt)
        .where(TestAttempt.id == attempt_id)
        .execution_options(populate_existing=True)
    )
    return await db.scalar(stmt)


async def start_attempt(
    db: AsyncSession, test_id: uuid.UUID, now: datetime, seed: int
) -> tuple[uuid.UUID, datetime]:
    stmt: Any = select(column("attempt_id"), column("deadline_at")).select_from(
        func.start_test_attempt(test_id, now, seed)
    )
    row = (await db.execute(stmt)).one()
    return row[0], row[1]


@dataclass(frozen=True)
class QuestionView:
    """A question without its answer."""

    id: uuid.UUID
    ordinal: int
    text: str
    options: list[str]


async def attempt_questions(db: AsyncSession, attempt_id: uuid.UUID) -> list[QuestionView]:
    stmt: Any = select(
        column("question_id"), column("ordinal"), column("text"), column("options")
    ).select_from(func.attempt_questions(attempt_id))
    return [
        QuestionView(r[0], int(r[1]), str(r[2]), [str(o) for o in r[3]])
        for r in (await db.execute(stmt)).all()
    ]


async def record_answer(
    db: AsyncSession, attempt_id: uuid.UUID, question_id: uuid.UUID, choice: int, now: datetime
) -> bool:
    value = await db.scalar(select(func.record_test_answer(attempt_id, question_id, choice, now)))
    return bool(value)


@dataclass(frozen=True)
class Score:
    score: Decimal
    correct: int
    total: int


async def score_attempt(db: AsyncSession, attempt_id: uuid.UUID, now: datetime) -> Score:
    stmt: Any = select(column("score"), column("correct"), column("total")).select_from(
        func.score_test_attempt(attempt_id, now)
    )
    row = (await db.execute(stmt)).one()
    return Score(Decimal(row[0]), int(row[1]), int(row[2]))


async def expired_open_attempts(db: AsyncSession, now: datetime, limit: int) -> list[uuid.UUID]:
    """Attempts past their deadline and never submitted (SYSTEM context, for auto-scoring)."""
    stmt = (
        select(TestAttempt.id)
        .where(TestAttempt.submitted_at.is_(None), TestAttempt.deadline_at < now)
        .order_by(TestAttempt.deadline_at)
        .limit(limit)
    )
    return list((await db.scalars(stmt)).all())
