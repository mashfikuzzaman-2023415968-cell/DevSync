"""Role assessment attempts for seeds and the test-only router (role assessment spec §14).

A seeded result is a real attempt: started, answered and scored through the same SECURITY
DEFINER functions the API uses, in the developer's own session — so seeded evidence, history
and flags look exactly like earned ones. The correct answers are read in a SYSTEM session (the
worker role may read the bank); that never happens in a request outside the test environment.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select

from app.algorithms.assessment_selection import Allocation, PoolQuestion, select_questions
from app.core.clock import get_clock
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.assessment import Competency, ReviewLevel
from app.models.profiles import Question, Skill, SkillEvidence, TestAttempt
from app.models.projects import Project, ProjectSlot
from app.repositories import role_assessments as repo
from app.services import role_assessments as svc

# Which questions to answer correctly: index, difficulty → correct?
Plan = Callable[[int, int], bool]


def all_correct(_index: int, _difficulty: int) -> bool:
    return True


def wrong_on(*indexes: int) -> Plan:
    return lambda index, _difficulty: index not in indexes


def every_other(index: int, _difficulty: int) -> bool:
    return index % 2 == 0


@dataclass(frozen=True)
class SeededAttempt:
    attempt_id: uuid.UUID
    evidence_id: uuid.UUID | None
    passed: bool | None
    overall_bp: int | None


async def _blueprint(project_id: uuid.UUID, slot_id: uuid.UUID) -> uuid.UUID:
    await svc.ensure_links_as_system(project_id)
    async with open_session(DbContext.system(), job=True) as db:
        links = await repo.slot_links(db, [slot_id])
        if slot_id not in links:
            raise LookupError("slot has no assessment blueprint")
        return links[slot_id].id


async def take(
    developer_id: uuid.UUID,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
    *,
    plan: Plan = all_correct,
    leaves: int = 0,
    stop_after: int | None = None,
    seed: int = 1,
) -> SeededAttempt:
    """Start and answer a role attempt as the developer. `leaves` sends that many focus events
    after `stop_after` answers (two end the attempt: the two-leave rule); otherwise every
    question is answered following `plan` and the last answer scores it."""
    blueprint_id = await _blueprint(project_id, slot_id)
    now = get_clock().now()
    token = secrets.token_urlsafe(svc.TOKEN_BYTES)
    token_hash = hashlib.sha256(token.encode()).digest()
    async with open_session(DbContext(user_id=developer_id, role="DEVELOPER")) as db:
        settings = await active_settings(db)
        bp = await repo.get_blueprint(db, blueprint_id)
        if bp is None:
            raise LookupError("blueprint not readable")
        pool = [
            PoolQuestion(r.question_id, r.competency_id, r.difficulty, r.times_served)
            for r in await repo.question_pool(db, bp.id, ReviewLevel.SELF_VERIFIED)
        ]
        allocations = [
            Allocation(
                c["competency_id"],
                c["code"],
                int(c["weight_bp"]),
                int(c["easy"]),
                int(c["medium"]),
                int(c["hard"]),
            )
            for c in bp.competencies
        ]
        selection = select_questions(allocations, pool, frozenset(), seed)
        a = settings.assessment
        attempt_id, _ = await repo.start(
            db,
            blueprint_id=bp.id,
            question_ids=selection.question_ids,
            now=now,
            seed=seed,
            project_id=project_id,
            slot_id=slot_id,
            token_hash=token_hash,
            extra_time=0,
            rules_version=svc.RULES_VERSION,
            retake_days=a.retake_days,
            leave_limit=a.leave_limit,
            validity_days=a.validity_days,
            reused_seen=selection.reused_seen,
            min_review=ReviewLevel.SELF_VERIFIED,
        )
        await db.commit()
    async with open_session(DbContext.system(), job=True) as sysdb:
        rows = await sysdb.execute(
            select(Question.id, Question.correct_index, Question.difficulty).where(
                Question.id.in_([uuid.UUID(q) for q in selection.question_ids])
            )
        )
        key = {qid: (int(idx), int(diff)) for qid, idx, diff in rows.all()}
    async with open_session(DbContext(user_id=developer_id, role="DEVELOPER")) as db:
        for index, raw in enumerate(selection.question_ids):
            if stop_after is not None and index >= stop_after:
                break
            qid = uuid.UUID(raw)
            correct, difficulty = key[qid]
            choice = correct if plan(index, difficulty) else (correct + 1) % 4
            await repo.record_answer(
                db, attempt_id, question_id=qid, choice=choice, now=now, token_hash=token_hash
            )
        for seq in range(1, leaves + 1):
            await repo.focus_event(
                db,
                attempt_id,
                seq=seq,
                kind="VISIBILITY_HIDDEN",
                now=now,
                client_at=None,
                fullscreen_supported=True,
                token_hash=token_hash,
            )
        await db.commit()
    async with open_session(DbContext.system(), job=True) as sysdb:
        attempt = await sysdb.get(TestAttempt, attempt_id)
        evidence = await sysdb.scalar(
            select(SkillEvidence).where(SkillEvidence.attempt_id == attempt_id)
        )
        return SeededAttempt(
            attempt_id,
            evidence.id if evidence is not None else None,
            attempt.passed if attempt is not None else None,
            attempt.overall_bp if attempt is not None else None,
        )


async def answer_key(attempt_id: uuid.UUID) -> list[dict[str, object]] | None:
    """Each question's position, competency and correct option of a role attempt (the test
    environment's walkthrough answers through the real UI with it; the demo stack uses the
    operator-only `scripts/demo_answer_key.py` instead, which has no HTTP route)."""
    async with open_session(DbContext.system(), job=True) as db:
        attempt = await db.get(TestAttempt, attempt_id)
        if attempt is None or attempt.blueprint_id is None:
            return None
        question_ids = list(attempt.question_ids)  # read before the session closes
        rows = await db.execute(
            select(Question.id, Question.correct_index, Competency.name)
            .outerjoin(Competency, Competency.id == Question.competency_id)
            .where(Question.id.in_(question_ids))
        )
        by_id = {qid: (int(idx), name) for qid, idx, name in rows.all()}
    return [
        {"index": i, "question_id": str(qid), "competency": by_id[qid][1], "answer": by_id[qid][0]}
        for i, qid in enumerate(question_ids)
    ]


async def slot_of(project_id: uuid.UUID, skill_name: str) -> uuid.UUID:
    """The first slot of a project for a skill (seeds name slots by skill)."""
    async with open_session(DbContext.system(), job=True) as db:
        slot = await db.scalar(
            select(ProjectSlot)
            .join(Skill, Skill.id == ProjectSlot.skill_id)
            .where(ProjectSlot.project_id == project_id, Skill.name == skill_name)
            .order_by(ProjectSlot.id)
        )
        project = await db.get(Project, project_id)
    if slot is None or project is None:
        raise LookupError(f"no {skill_name} slot")
    return slot.id
