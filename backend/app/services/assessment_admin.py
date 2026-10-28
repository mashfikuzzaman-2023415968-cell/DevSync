"""Admin tools for role assessments (role assessment spec §12).

- Flagged attempts: the queue, the full detail (focus events, gaps, per-question correctness and
  response times), **void** (step-up; the evidence stops counting, affected bids are re-evaluated
  and their bidders told, an immediate retake is allowed) and **mark reviewed**.
- Accommodations: 25 % or 50 % extra time for a developer's later attempts (step-up).
- Question bank review: list and inspect, edit drafts, **approve** (HUMAN_APPROVED, named) and
  **retire** (never below a practice test's question count). An approved question's content is
  immutable (trigger); a correction is a new version.

Admins act through RLS (admin policies) except where a definer function is the only writer
(void, mark reviewed). Every action is audited.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.core.audit import write_audit
from app.core.clock import get_clock
from app.core.errors import DomainError, ErrorCode, NotFoundError
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.assessment import (
    AssessmentBlueprint,
    AttemptKind,
    Competency,
    QuestionStatus,
    ReviewLevel,
    UserAccommodation,
)
from app.models.bidding import Bid, BidStatus
from app.models.identity import User
from app.models.profiles import Question, Skill, SkillEvidence, SkillTest, TestAttempt
from app.models.projects import Project
from app.repositories import role_assessments as repo
from app.schemas.assessment_admin import (
    AccommodationIn,
    AccommodationOut,
    AnswerTraceOut,
    AttemptDetailOut,
    FlaggedItemOut,
    QuestionAdminOut,
    QuestionPatch,
    VoidIn,
    VoidOut,
)
from app.services import bids as bids_svc
from app.services.context import Ctx
from app.services.notifications import notify_users

MAX_LIST = 200


def _require_step_up(ctx: Ctx) -> None:
    if not ctx.principal.has_step_up(ctx.now):
        raise DomainError(code=ErrorCode.STEP_UP_REQUIRED)


async def _audit(
    ctx: Ctx, action: str, entity_type: str, entity_id: uuid.UUID, **after: object
) -> None:
    await write_audit(
        ctx.db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        after=dict(after) or None,
    )


# ------------------------------------------------------------------------ flagged attempts


def _item(a: TestAttempt, name: str, label: str, voided: SkillEvidence | None) -> FlaggedItemOut:
    return FlaggedItemOut(
        attempt_id=a.id,
        candidate_id=a.user_id,
        candidate_name=name,
        label=label,
        started_at=a.started_at,
        submitted_at=a.submitted_at,
        score=(a.overall_bp // 100) if a.overall_bp is not None else None,
        passed=a.passed,
        terminated_reason=a.terminated_reason.value if a.terminated_reason else None,
        flagged=a.flagged,
        focus_leaves=a.focus_leaves,
        connection_gaps=a.connection_gaps,
        reviewed_at=a.admin_reviewed_at,
        voided=voided is not None and voided.voided_at is not None,
    )


async def list_attempts(
    ctx: Ctx,
    *,
    flagged: bool | None,
    since: datetime | None,
    until: datetime | None,
    skill_id: uuid.UUID | None,
) -> list[FlaggedItemOut]:
    stmt = (
        select(TestAttempt, User.display_name, AssessmentBlueprint.label, SkillEvidence)
        .join(User, User.id == TestAttempt.user_id)
        .join(AssessmentBlueprint, AssessmentBlueprint.id == TestAttempt.blueprint_id)
        .outerjoin(SkillEvidence, SkillEvidence.attempt_id == TestAttempt.id)
        .where(TestAttempt.kind == AttemptKind.ROLE)
    )
    if flagged is not None:
        stmt = stmt.where(TestAttempt.flagged.is_(flagged))
    if since is not None:
        stmt = stmt.where(TestAttempt.started_at >= since)
    if until is not None:
        stmt = stmt.where(TestAttempt.started_at < until)
    if skill_id is not None:
        stmt = stmt.where(AssessmentBlueprint.primary_skill_id == skill_id)
    stmt = stmt.order_by(TestAttempt.started_at.desc()).limit(MAX_LIST)
    return [_item(a, n, label, e) for a, n, label, e in (await ctx.db.execute(stmt)).all()]


async def _role_attempt(ctx: Ctx, attempt_id: uuid.UUID) -> TestAttempt:
    attempt = await repo.get_attempt(ctx.db, attempt_id)
    if attempt is None:
        raise NotFoundError
    return attempt


def _answers(
    a: TestAttempt, questions: dict[uuid.UUID, Question], names: dict[uuid.UUID, str]
) -> list[AnswerTraceOut]:
    locked = {uuid.UUID(str(x["question_id"])): x for x in a.answers_locked}
    out: list[AnswerTraceOut] = []
    previous = a.started_at
    for i, qid in enumerate(a.question_ids):
        q = questions[qid]
        entry = locked.get(qid)
        at = datetime.fromisoformat(str(entry["answered_at"])) if entry else None
        choice = entry.get("choice") if entry else None
        out.append(
            AnswerTraceOut(
                index=i,
                question_id=qid,
                slug=q.slug,
                competency=names.get(q.competency_id) if q.competency_id else None,
                difficulty=q.difficulty,
                choice=choice,
                correct=choice is not None and int(choice) == q.correct_index,
                answered_at=at,
                seconds=int((at - previous).total_seconds()) if at else None,
            )
        )
        previous = at or previous
    return out


async def attempt_detail(ctx: Ctx, attempt_id: uuid.UUID) -> AttemptDetailOut:
    a = await _role_attempt(ctx, attempt_id)
    user = await ctx.db.get(User, a.user_id)
    bp = await ctx.db.get(AssessmentBlueprint, a.blueprint_id)
    evidence = await ctx.db.scalar(select(SkillEvidence).where(SkillEvidence.attempt_id == a.id))
    questions = {
        q.id: q
        for q in (
            await ctx.db.scalars(select(Question).where(Question.id.in_(a.question_ids)))
        ).all()
    }
    names = dict((await ctx.db.execute(select(Competency.id, Competency.name))).tuples().all())
    base = _item(a, user.display_name if user else "Developer", bp.label if bp else "", evidence)
    return AttemptDetailOut(
        **base.model_dump(),
        deadline_at=a.deadline_at,
        extra_time_seconds=a.extra_time_seconds,
        reused_seen=a.reused_seen,
        focus_events=list(a.focus_events),
        last_heartbeat_at=a.last_heartbeat_at,
        breakdown=list(a.breakdown or []),
        answers=_answers(a, questions, names),
        void_reason=evidence.void_reason if evidence else None,
    )


async def _reevaluate(evidence_ids: Sequence[uuid.UUID]) -> int:
    """Bids that relied on voided evidence: their bidders are told; projects whose bidding has
    already closed get Algorithm 1's verdict recorded again (§8.3 "re-evaluated")."""
    if not evidence_ids:
        return 0
    async with open_session(DbContext.system(), job=True) as sysdb:
        bids = list(
            (
                await sysdb.scalars(
                    select(Bid).where(
                        Bid.assessment_evidence_id.in_(list(evidence_ids)),
                        Bid.status.in_([BidStatus.ACTIVE, BidStatus.INELIGIBLE]),
                    )
                )
            ).all()
        )
        settings = await active_settings(sysdb)
        now = get_clock().now()
        for project_id in {b.project_id for b in bids}:
            project = await sysdb.get(Project, project_id)
            if project is not None and bids_svc.bidding_closed(project, now):
                ev = await bids_svc.evaluate(sysdb, project, settings, now.date())
                bids_svc.record_evaluation(ev, now)
        await sysdb.commit()
        notified = [(b.developer_id, b.id) for b in bids]
    for developer_id, bid_id in notified:
        await notify_users(
            [developer_id],
            "ROLE_ASSESSMENT_VOIDED",
            title="Your role assessment was voided",
            body="An admin voided the role assessment this bid relied on, so it is no longer "
            "eligible. You can take the assessment again now.",
            link=f"/dev/bids/{bid_id}",
        )
    return len(notified)


async def void_attempt(ctx: Ctx, attempt_id: uuid.UUID, body: VoidIn) -> VoidOut:
    """Void with step-up (§12.1, §16 case 43): the evidence stops counting, an immediate retake
    is allowed, bids relying on it are re-evaluated and their bidders told."""
    _require_step_up(ctx)
    await _role_attempt(ctx, attempt_id)
    try:
        rows = await repo.void(ctx.db, attempt_id, body.reason, ctx.now)
    except DBAPIError as exc:
        await ctx.db.rollback()
        raise DomainError(code=ErrorCode.INVALID_STATE) from exc
    await _audit(
        ctx, "role_assessment.void", "test_attempt", attempt_id, reason_length=len(body.reason)
    )
    await ctx.db.commit()
    affected = await _reevaluate([evidence_id for _, _, evidence_id in rows])
    return VoidOut(attempt_id=attempt_id, voided_at=ctx.now, bids_affected=affected)


async def mark_reviewed(ctx: Ctx, attempt_id: uuid.UUID) -> FlaggedItemOut:
    await _role_attempt(ctx, attempt_id)
    await repo.mark_reviewed(ctx.db, attempt_id, ctx.now)
    await _audit(ctx, "role_assessment.review", "test_attempt", attempt_id)
    await ctx.db.commit()
    detail = await attempt_detail(ctx, attempt_id)
    return FlaggedItemOut(**detail.model_dump(include=set(FlaggedItemOut.model_fields)))


# ---------------------------------------------------------------------- accommodations


async def set_accommodation(
    ctx: Ctx, user_id: uuid.UUID, body: AccommodationIn
) -> AccommodationOut:
    """Extra time for attempts started from now on (§12.3); step-up and audited."""
    _require_step_up(ctx)
    user = await ctx.db.get(User, user_id)
    if user is None or user.role.value != "DEVELOPER":
        raise NotFoundError
    row = await ctx.db.get(UserAccommodation, user_id)
    if row is None:
        row = UserAccommodation(user_id=user_id)
        ctx.db.add(row)
    row.extra_time_pct = body.extra_time_pct
    row.note = body.note.strip()
    row.granted_by = ctx.uid
    row.granted_at = ctx.now
    await ctx.db.flush()
    await _audit(
        ctx, "role_assessment.accommodation", "user", user_id, extra_time_pct=body.extra_time_pct
    )
    await ctx.db.commit()
    return AccommodationOut(
        user_id=user_id, extra_time_pct=row.extra_time_pct, note=row.note, granted_at=row.granted_at
    )


# --------------------------------------------------------------------- question bank


async def _question_out(ctx: Ctx, q: Question) -> QuestionAdminOut:
    skill = await ctx.db.get(Skill, q.skill_id)
    comp = await ctx.db.get(Competency, q.competency_id) if q.competency_id else None
    return QuestionAdminOut(
        id=q.id,
        slug=q.slug,
        skill=skill.name if skill else "",
        competency_id=q.competency_id,
        competency=comp.name if comp else None,
        difficulty=q.difficulty,
        text=q.text,
        code_snippet=q.code_snippet,
        options=list(q.options),
        correct_index=q.correct_index,
        explanation=q.explanation,
        status=q.status.value,
        source=q.source.value,
        review_level=q.review_level.value,
        reviewed_by_name=q.reviewed_by_name,
        reviewed_at=q.reviewed_at,
        verification=q.verification,
        active=q.active,
        times_served=q.times_served,
        version=q.version,
    )


async def list_questions(
    ctx: Ctx,
    *,
    skill_id: uuid.UUID | None,
    competency_id: uuid.UUID | None,
    difficulty: int | None,
    status: str | None,
    source: str | None,
    offset: int,
    limit: int,
) -> list[QuestionAdminOut]:
    stmt = select(Question)
    if skill_id is not None:
        stmt = stmt.where(Question.skill_id == skill_id)
    if competency_id is not None:
        stmt = stmt.where(Question.competency_id == competency_id)
    if difficulty is not None:
        stmt = stmt.where(Question.difficulty == difficulty)
    if status is not None:
        stmt = stmt.where(Question.status == QuestionStatus(status))
    if source is not None:
        stmt = stmt.where(Question.source == source)
    stmt = stmt.order_by(Question.slug, Question.id).offset(offset).limit(min(limit, MAX_LIST))
    return [await _question_out(ctx, q) for q in (await ctx.db.scalars(stmt)).all()]


async def _question(ctx: Ctx, question_id: uuid.UUID, *, lock: bool = False) -> Question:
    stmt = select(Question).where(Question.id == question_id)
    if lock:
        stmt = stmt.with_for_update()
    q = await ctx.db.scalar(stmt.execution_options(populate_existing=True))
    if q is None:
        raise NotFoundError
    return q


async def get_question(ctx: Ctx, question_id: uuid.UUID) -> QuestionAdminOut:
    return await _question_out(ctx, await _question(ctx, question_id))


async def edit_question(ctx: Ctx, question_id: uuid.UUID, body: QuestionPatch) -> QuestionAdminOut:
    q = await _question(ctx, question_id, lock=True)
    if q.status != QuestionStatus.DRAFT:
        raise DomainError(
            "An approved question can't be edited: retire it and add a corrected version.",
            code=ErrorCode.INVALID_STATE,
        )
    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(q, name, value)
    q.version += 1
    await _audit(ctx, "question.edit", "question", q.id)
    await ctx.db.commit()
    return await get_question(ctx, question_id)


async def approve_question(ctx: Ctx, question_id: uuid.UUID) -> QuestionAdminOut:
    """Human approval by the admin (§12.2): APPROVED, HUMAN_APPROVED, named."""
    q = await _question(ctx, question_id, lock=True)
    if q.status == QuestionStatus.RETIRED:
        raise DomainError("A retired question can't be approved.", code=ErrorCode.INVALID_STATE)
    if q.competency_id is None or not q.explanation:
        raise DomainError(
            "Give the question a competency and an explanation before approving it.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"competency_id": "required", "explanation": "required"},
        )
    admin = await ctx.db.get(User, ctx.uid)
    q.status = QuestionStatus.APPROVED
    q.review_level = ReviewLevel.HUMAN_APPROVED
    q.reviewed_by_user = ctx.uid
    q.reviewed_by_name = admin.display_name if admin else "Admin"
    q.reviewed_at = ctx.now
    await _audit(ctx, "question.approve", "question", q.id)
    await ctx.db.commit()
    return await get_question(ctx, question_id)


async def retire_question(ctx: Ctx, question_id: uuid.UUID) -> QuestionAdminOut:
    """Retire (§12.2): refused if a practice test would be left with too few active questions."""
    q = await _question(ctx, question_id, lock=True)
    if q.status == QuestionStatus.RETIRED:
        return await _question_out(ctx, q)
    if q.active:
        test = await ctx.db.scalar(select(SkillTest).where(SkillTest.skill_id == q.skill_id))
        active = await ctx.db.scalar(
            select(func.count()).where(Question.skill_id == q.skill_id, Question.active.is_(True))
        )
        if test is not None and (active or 0) - 1 < test.question_count:
            raise DomainError(
                f"Retiring it would leave the {test.title} with fewer than "
                f"{test.question_count} questions. Add a practice question first.",
                code=ErrorCode.INVALID_STATE,
            )
    q.status = QuestionStatus.RETIRED
    q.active = False
    await _audit(ctx, "question.retire", "question", q.id)
    await ctx.db.commit()
    return await get_question(ctx, question_id)
