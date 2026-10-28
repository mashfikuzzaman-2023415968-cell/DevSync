"""Role assessment queries (role assessment spec §10).

Attempts, blueprints and evidence are written only through the SECURITY DEFINER functions of
migration 0011; questions leave the database one at a time (`role_current_question`) and never
with their answers. Domain refusals raised by those functions carry SQLSTATE P0001 and the error
code as the message (see `domain_code`).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import column, func, literal, select
from sqlalchemy.dialects.postgresql import BYTEA, ENUM, JSONB
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import (
    AssessmentBlueprint,
    AttemptKind,
    Competency,
    ReviewLevel,
    SlotAssessment,
    UserAccommodation,
)
from app.models.profiles import EvidenceSource, SkillEvidence, TestAttempt

_REVIEW = ENUM(ReviewLevel, name="review_level", create_type=False,
               values_callable=lambda e: [m.value for m in e])  # fmt: skip


def _review(level: ReviewLevel) -> Any:
    return literal(level.value, type_=_REVIEW)


def _bytes(value: bytes | None) -> Any:
    return literal(value, type_=BYTEA)


def sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def domain_code(exc: DBAPIError) -> tuple[str | None, dict[str, Any]]:
    """The domain code (P0001 message) and its JSON detail, if the function raised one."""
    if sqlstate(exc) != "P0001":
        return None, {}
    diag = getattr(exc.orig, "diag", None)
    message = getattr(diag, "message_primary", None)
    detail = getattr(diag, "message_detail", None)
    try:
        extra = json.loads(detail) if detail else {}
    except ValueError:
        extra = {}
    return message, extra if isinstance(extra, dict) else {}


# ------------------------------------------------------------------------------ catalogue


async def competencies(db: AsyncSession) -> Sequence[Competency]:
    stmt = select(Competency).where(Competency.active.is_(True)).order_by(Competency.position)
    return (await db.scalars(stmt)).all()


async def bank_counts(
    db: AsyncSession, skill_ids: Sequence[uuid.UUID], min_review: ReviewLevel
) -> dict[tuple[str, int], int]:
    stmt: Any = select(column("competency_id"), column("difficulty"), column("approved")).select_from(
        func.role_bank_counts(list(skill_ids), _review(min_review))
    )
    return {(str(r[0]), int(r[1])): int(r[2]) for r in (await db.execute(stmt)).all()}


@dataclass(frozen=True)
class PoolRow:
    question_id: str
    competency_id: str
    difficulty: int
    times_served: int


async def question_pool(
    db: AsyncSession, blueprint_id: uuid.UUID, min_review: ReviewLevel
) -> list[PoolRow]:
    stmt: Any = select(
        column("question_id"), column("competency_id"), column("difficulty"), column("times_served")
    ).select_from(func.role_question_pool(blueprint_id, _review(min_review)))
    return [
        PoolRow(str(r[0]), str(r[1]), int(r[2]), int(r[3])) for r in (await db.execute(stmt)).all()
    ]


async def recent_questions(db: AsyncSession, since: datetime) -> frozenset[str]:
    stmt: Any = select(column("question_id")).select_from(func.user_recent_questions(since))
    return frozenset(str(r[0]) for r in (await db.execute(stmt)).all())


# ----------------------------------------------------------------------------- blueprints


async def create_slot_assessment(
    db: AsyncSession,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
    blueprint: dict[str, Any],
    requirements_hash: str,
) -> uuid.UUID:
    value = await db.scalar(
        select(
            func.create_slot_assessment(
                project_id, slot_id, func.cast(json.dumps(blueprint), JSONB), requirements_hash
            )
        )
    )
    return uuid.UUID(str(value))



async def slot_links(
    db: AsyncSession, slot_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, AssessmentBlueprint]:
    if not slot_ids:
        return {}
    stmt = (
        select(SlotAssessment.slot_id, AssessmentBlueprint)
        .join(AssessmentBlueprint, AssessmentBlueprint.id == SlotAssessment.blueprint_id)
        .where(SlotAssessment.slot_id.in_(list(slot_ids)))
    )
    return {slot: bp for slot, bp in (await db.execute(stmt)).all()}


async def get_blueprint(db: AsyncSession, blueprint_id: uuid.UUID) -> AssessmentBlueprint | None:
    return await db.scalar(select(AssessmentBlueprint).where(AssessmentBlueprint.id == blueprint_id))


async def blueprints(
    db: AsyncSession, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, AssessmentBlueprint]:
    if not ids:
        return {}
    stmt = select(AssessmentBlueprint).where(AssessmentBlueprint.id.in_(list(ids)))
    return {b.id: b for b in (await db.scalars(stmt)).all()}


# ------------------------------------------------------------------------------- attempts


async def get_attempt(db: AsyncSession, attempt_id: uuid.UUID) -> TestAttempt | None:
    """A role attempt the caller may read (RLS: owner or admin), always re-read."""
    stmt = (
        select(TestAttempt)
        .where(TestAttempt.id == attempt_id, TestAttempt.kind == AttemptKind.ROLE)
        .execution_options(populate_existing=True)
    )
    return await db.scalar(stmt)


async def open_attempts(db: AsyncSession, user_id: uuid.UUID) -> Sequence[TestAttempt]:
    """Every attempt (practice or role) of the user not yet scored, newest first."""
    stmt = (
        select(TestAttempt)
        .where(TestAttempt.user_id == user_id, TestAttempt.submitted_at.is_(None))
        .order_by(TestAttempt.started_at.desc())
        .execution_options(populate_existing=True)
    )
    return (await db.scalars(stmt)).all()


async def role_attempts(
    db: AsyncSession, user_id: uuid.UUID, blueprint_id: uuid.UUID | None = None
) -> Sequence[TestAttempt]:
    stmt = select(TestAttempt).where(
        TestAttempt.user_id == user_id, TestAttempt.kind == AttemptKind.ROLE
    )
    if blueprint_id is not None:
        stmt = stmt.where(TestAttempt.blueprint_id == blueprint_id)
    stmt = stmt.order_by(TestAttempt.started_at.desc()).execution_options(populate_existing=True)
    return (await db.scalars(stmt)).all()


async def start(
    db: AsyncSession,
    *,
    blueprint_id: uuid.UUID,
    question_ids: Sequence[str],
    now: datetime,
    seed: int,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
    token_hash: bytes,
    extra_time: int,
    rules_version: int,
    retake_days: int,
    leave_limit: int,
    validity_days: int,
    reused_seen: bool,
    min_review: ReviewLevel,
) -> tuple[uuid.UUID, datetime]:
    stmt: Any = select(column("attempt_id"), column("deadline_at")).select_from(
        func.start_role_attempt(
            blueprint_id, [uuid.UUID(q) for q in question_ids], now, seed, project_id, slot_id,
            _bytes(token_hash), extra_time, rules_version, retake_days, leave_limit,
            validity_days, reused_seen, _review(min_review),
        )
    )  # fmt: skip
    row = (await db.execute(stmt)).one()
    return row[0], row[1]


@dataclass(frozen=True)
class CurrentQuestion:
    index: int
    total: int
    question_id: uuid.UUID
    text: str
    code_snippet: str | None
    options: list[str]
    competency_name: str | None


async def current_question(
    db: AsyncSession, attempt_id: uuid.UUID, token_hash: bytes
) -> CurrentQuestion | None:
    stmt: Any = select(
        column("idx"), column("total"), column("question_id"), column("text"),
        column("code_snippet"), column("options"), column("competency_name"),
    ).select_from(func.role_current_question(attempt_id, _bytes(token_hash)))  # fmt: skip
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        return None
    return CurrentQuestion(
        int(row[0]), int(row[1]), row[2], str(row[3]), row[4], [str(o) for o in row[5]], row[6]
    )


async def record_answer(
    db: AsyncSession,
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
    choice: int | None,
    now: datetime,
    token_hash: bytes,
) -> tuple[str, int]:
    stmt: Any = select(column("status"), column("current_index")).select_from(
        func.record_role_answer(attempt_id, question_id, choice, now, _bytes(token_hash))
    )
    row = (await db.execute(stmt)).one()
    return str(row[0]), int(row[1])


async def finish(db: AsyncSession, attempt_id: uuid.UUID, now: datetime, token_hash: bytes) -> str:
    return str(await db.scalar(select(func.finish_role_attempt(attempt_id, now, _bytes(token_hash)))))


async def focus_event(
    db: AsyncSession,
    attempt_id: uuid.UUID,
    *,
    seq: int,
    kind: str,
    now: datetime,
    client_at: datetime | None,
    fullscreen_supported: bool | None,
    token_hash: bytes,
) -> tuple[str, int]:
    stmt: Any = select(column("status"), column("focus_leaves")).select_from(
        func.record_focus_event(
            attempt_id, seq, kind, now, client_at, fullscreen_supported, _bytes(token_hash)
        )
    )
    row = (await db.execute(stmt)).one()
    return str(row[0]), int(row[1])


async def heartbeat(
    db: AsyncSession, attempt_id: uuid.UUID, now: datetime, token_hash: bytes
) -> str:
    return str(await db.scalar(select(func.record_heartbeat(attempt_id, now, _bytes(token_hash)))))


async def rotate_token(
    db: AsyncSession, attempt_id: uuid.UUID, new_hash: bytes, now: datetime
) -> str:
    return str(await db.scalar(select(func.rotate_attempt_token(attempt_id, _bytes(new_hash), now))))


async def score(db: AsyncSession, attempt_id: uuid.UUID, now: datetime) -> str:
    return str(await db.scalar(select(func.score_role_attempt(attempt_id, now))))


async def void(
    db: AsyncSession, attempt_id: uuid.UUID, reason: str, now: datetime
) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    stmt: Any = select(column("user_id"), column("blueprint_id"), column("evidence_id")).select_from(
        func.void_role_attempt(attempt_id, reason, now)
    )
    return [(r[0], r[1], r[2]) for r in (await db.execute(stmt)).all()]


async def mark_reviewed(db: AsyncSession, attempt_id: uuid.UUID, now: datetime) -> bool:
    return bool(await db.scalar(select(func.mark_role_attempt_reviewed(attempt_id, now))))


async def expired_open(db: AsyncSession, now: datetime, limit: int) -> list[uuid.UUID]:
    """Role attempts past their deadline (+ grace, applied by the caller) and never scored."""
    stmt = (
        select(TestAttempt.id)
        .where(
            TestAttempt.kind == AttemptKind.ROLE,
            TestAttempt.submitted_at.is_(None),
            TestAttempt.deadline_at < now,
        )
        .order_by(TestAttempt.deadline_at)
        .limit(limit)
    )
    return list((await db.scalars(stmt)).all())


# ------------------------------------------------------------------------------- evidence


async def evidence_for(
    db: AsyncSession, user_ids: Sequence[uuid.UUID], blueprint_ids: Sequence[uuid.UUID]
) -> Sequence[SkillEvidence]:
    """ROLE_ASSESSMENT evidence of these users for these blueprints, newest first."""
    if not user_ids or not blueprint_ids:
        return []
    stmt = (
        select(SkillEvidence)
        .where(
            SkillEvidence.source == EvidenceSource.ROLE_ASSESSMENT,
            SkillEvidence.user_id.in_(list(user_ids)),
            SkillEvidence.blueprint_id.in_(list(blueprint_ids)),
        )
        .order_by(SkillEvidence.at.desc())
        .execution_options(populate_existing=True)
    )
    return (await db.scalars(stmt)).all()


async def evidence_by_ids(db: AsyncSession, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, SkillEvidence]:
    if not ids:
        return {}
    stmt = select(SkillEvidence).where(SkillEvidence.id.in_(list(ids)))
    return {e.id: e for e in (await db.scalars(stmt)).all()}


async def attempts_by_ids(db: AsyncSession, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, TestAttempt]:
    if not ids:
        return {}
    stmt = select(TestAttempt).where(TestAttempt.id.in_(list(ids)))
    return {a.id: a for a in (await db.scalars(stmt)).all()}


async def accommodation(db: AsyncSession, user_id: uuid.UUID) -> UserAccommodation | None:
    return await db.scalar(select(UserAccommodation).where(UserAccommodation.user_id == user_id))
