"""Role assessment for newcomers (ROLE_ASSESSMENT_BUILD_SPEC.md §5–§8).

A newcomer bidding for a project slot takes an assessment built from that slot's **blueprint**:
the same competencies, weights, questions per difficulty, time and pass rule for everyone who
bids for the role. The blueprint is built by `algorithms/role_blueprint.py` from the project's own
data when the project is published, and frozen; the questions of an attempt are chosen by
`algorithms/assessment_selection.py` from the approved bank and validated, served one at a time,
answered and scored by the SECURITY DEFINER functions of migration 0011 — the server decides the
deadline, the current question and the result, and answers never reach this process.

Every request about an attempt carries the window token (`X-Attempt-Token`, §6.6): issued on
start or resume, stored hashed, compared in constant time here and again in SQL. A request about
an open attempt whose deadline (+ 5 s grace) has passed scores it first (§6.3).

The bids service asks `newcomer_evidence` for each newcomer bid's evidence (a role result for the
slot's blueprint, or the practice result where no assessment is available, Decision 10) and
`require_for_bid` before a newcomer's bid is placed or moved to another slot (§8.3).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms import role_blueprint as rb
from app.algorithms.assessment_selection import (
    Allocation,
    PoolQuestion,
    Selection,
    SelectionUnavailable,
    select_questions,
)
from app.core import idempotency
from app.core.audit import write_audit
from app.core.authz import authorize
from app.core.errors import DomainError, ErrorCode, NotFoundError
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.assessment import (
    AssessmentBlueprint,
    BlueprintStatus,
    ReviewLevel,
    TerminatedReason,
)
from app.models.profiles import Skill, SkillEvidence, TestAttempt
from app.models.projects import Project, ProjectSlot, ProjectStatus
from app.repositories import bids as bidrepo
from app.repositories import projects as projrepo
from app.repositories import role_assessments as repo
from app.schemas.platform_settings import PlatformSettingsValues
from app.schemas.role_assessments import (
    AnswerIn,
    AnswerOut,
    AssessmentResultOut,
    AssessmentStatusOut,
    AttemptStateOut,
    BlueprintCompetencyOut,
    BlueprintOut,
    CompetencyScoreOut,
    FallbackOut,
    FocusEventIn,
    FocusEventOut,
    HeartbeatOut,
    HistoryItemOut,
    QuestionOut,
    StartedOut,
    StartIn,
)
from app.services import reputation_read
from app.services.context import Ctx

RULES_VERSION = 1  # the consent screen's rules (§7.1); bump when the text changes
GRACE = timedelta(seconds=5)  # answers up to 5 s after the deadline still count (§6.3)
RECENT_WINDOW = timedelta(days=180)  # questions seen this recently are avoided (§5.2)
CLOSES_SOON_MARGIN = timedelta(minutes=5)  # §6.2 "bidding closes before now + limit + 5 min"
CLIENT_CLOCK_WINDOW = timedelta(days=1)  # a focus event's client time further off is dropped
SEED_BITS = 62
TOKEN_BYTES = 32  # 256-bit window token (§6.6)
MAX_TOKEN_LENGTH = 100

Kind = Literal["ROLE", "PRACTICE"]


# ----------------------------------------------------------------------------- settings


def min_review(settings: PlatformSettingsValues) -> ReviewLevel:
    """Questions usable now: human-approved only once the team review is switched on (§13.3)."""
    return (
        ReviewLevel.HUMAN_APPROVED
        if settings.assessment.require_human_review
        else ReviewLevel.SELF_VERIFIED
    )


def blueprint_params(settings: PlatformSettingsValues) -> rb.BlueprintParams:
    a = settings.assessment
    easy, medium, hard = a.difficulty_mix
    return rb.BlueprintParams(
        question_count=a.question_count,
        time_limit_seconds=a.time_limit_seconds,
        difficulty_mix=rb.DifficultyMix(easy, medium, hard),
        pass_rule=rb.PassRule(a.pass_overall_bp, a.floor_bp, a.heavy_weight_bp),
        min_approved_per_competency=a.min_approved_per_competency,
    )


def _newcomer_rule_on(settings: PlatformSettingsValues) -> bool:
    return settings.algorithm.mode == "devsync"  # pcs_replication has no newcomer rule (§1.5)


# --------------------------------------------------------------------------- blueprints


def _text(project: Project) -> str:
    return "\n".join(
        part
        for part in (project.title, project.summary, project.description, project.requirements)
        if part
    )


def _payload(result: rb.Blueprint | rb.Unavailable, params: rb.BlueprintParams) -> dict[str, Any]:
    if isinstance(result, rb.Unavailable):
        return {
            "algo_version": result.algo_version,
            "fingerprint": result.fingerprint,
            "primary_skill_id": result.primary_skill_id,
            "label": result.label,
            "competencies": [],
            "question_count": params.question_count,
            "time_limit_seconds": result.time_limit_seconds,
            "difficulty_mix": params.difficulty_mix.as_dict(),
            "pass_rule": result.pass_rule.as_dict(),
            "status": BlueprintStatus.UNAVAILABLE.value,
            "unavailable_reason": result.reason.value,
        }
    return {
        "algo_version": result.algo_version,
        "fingerprint": result.fingerprint,
        "primary_skill_id": result.primary_skill_id,
        "label": result.label,
        "competencies": [
            {
                "competency_id": c.competency_id,
                "skill_id": c.skill_id,
                "code": c.code,
                "name": c.name,
                "weight_bp": c.weight_bp,
                "question_count": c.question_count,
                "easy": c.easy,
                "medium": c.medium,
                "hard": c.hard,
                "reasons": list(c.reasons),
            }
            for c in result.competencies
        ],
        "question_count": result.question_count,
        "time_limit_seconds": result.time_limit_seconds,
        "difficulty_mix": result.difficulty_mix.as_dict(),
        "pass_rule": result.pass_rule.as_dict(),
        "status": BlueprintStatus.AVAILABLE.value,
        "unavailable_reason": None,
    }


async def ensure_slot_assessments(
    db: AsyncSession, project: Project, settings: PlatformSettingsValues
) -> dict[uuid.UUID, AssessmentBlueprint]:
    """Link every slot of the project to its blueprint (built and frozen on first need). Runs in
    the publish transaction as the project's client, or as SYSTEM for projects published before
    this feature; links that exist are kept as they are (§4.4)."""
    slots = list(await projrepo.load_slots(db, project.id))
    links = await repo.slot_links(db, [s.id for s in slots])
    missing = [s for s in slots if s.id not in links]
    if not missing:
        return links
    milestones = list(await projrepo.load_milestones(db, project.id))
    skills_of = await projrepo.load_milestone_skills(db, [m.id for m in milestones])
    milestone_sets = [frozenset(str(x) for x in skills_of.get(m.id, [])) for m in milestones]
    names = {str(i): n for i, n in (await db.execute(select(Skill.id, Skill.name))).tuples()}
    catalogue: dict[str, list[rb.Competency]] = {}
    for c in await repo.competencies(db):
        catalogue.setdefault(str(c.skill_id), []).append(
            rb.Competency(
                id=str(c.id),
                skill_id=str(c.skill_id),
                code=c.code,
                name=c.name,
                is_core=c.is_core,
                keywords=tuple(c.keywords),
                position=c.position,
            )
        )
    counts = await repo.bank_counts(db, [uuid.UUID(s) for s in names], min_review(settings))
    params = blueprint_params(settings)
    text = _text(project)
    for slot in missing:
        inp = rb.BlueprintInput(
            primary_skill_id=str(slot.skill_id),
            skill_names=names,
            milestones=milestone_sets,
            text=text,
            catalogue=catalogue,
            bank_counts=counts,
            params=params,
        )
        result = rb.build_blueprint(inp)
        requirements = hashlib.sha256(
            json.dumps(
                {
                    "skill": str(slot.skill_id),
                    "milestones": sorted(sorted(m) for m in milestone_sets),
                    "text": rb.normalise_text(text),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        await repo.create_slot_assessment(
            db, project.id, slot.id, _payload(result, params), requirements
        )
        if isinstance(result, rb.Blueprint):
            await write_audit(
                db,
                action="blueprint.create",
                entity_type="project_slot",
                entity_id=slot.id,
                after={"fingerprint": result.fingerprint[:12], "label": result.label},
            )
    return await repo.slot_links(db, [s.id for s in slots])


async def ensure_links_as_system(project_id: uuid.UUID) -> None:
    """Create missing slot links for a published project in a SYSTEM session of its own (a
    developer or client request can't insert them; the result is the same as at publish)."""
    async with open_session(DbContext.system(), job=True) as sysdb:
        project = await projrepo.get_project(sysdb, project_id)
        if project is None or project.status == ProjectStatus.DRAFT:
            return
        settings = await active_settings(sysdb)
        await ensure_slot_assessments(sysdb, project, settings)
        await sysdb.commit()


async def _links(
    db: AsyncSession, project: Project, slots: Sequence[ProjectSlot]
) -> dict[uuid.UUID, AssessmentBlueprint]:
    links = await repo.slot_links(db, [s.id for s in slots])
    if len(links) < len(slots) and project.status != ProjectStatus.DRAFT:
        await ensure_links_as_system(project.id)
        links = await repo.slot_links(db, [s.id for s in slots])
    return links


def _allocations(bp: AssessmentBlueprint) -> list[Allocation]:
    return [
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


async def _select(
    db: AsyncSession,
    bp: AssessmentBlueprint,
    settings: PlatformSettingsValues,
    recent: frozenset[str],
    seed: int,
) -> Selection | None:
    """The selector run against the pool as it is now (§5.4): None when it can't be served."""
    if bp.status != BlueprintStatus.AVAILABLE:
        return None
    pool = [
        PoolQuestion(r.question_id, r.competency_id, r.difficulty, r.times_served)
        for r in await repo.question_pool(db, bp.id, min_review(settings))
    ]
    try:
        return select_questions(_allocations(bp), pool, recent, seed)
    except SelectionUnavailable:
        return None


async def available_now(
    db: AsyncSession, bp: AssessmentBlueprint, settings: PlatformSettingsValues
) -> bool:
    return await _select(db, bp, settings, frozenset(), 0) is not None


# ------------------------------------------------------------------------------- results


def _pct(bp_value: int) -> int:
    return bp_value // 100


def _named(attempt: TestAttempt, pick: str) -> str | None:
    rows = attempt.breakdown or []
    if not rows:
        return None
    if pick == "strongest":
        best = min(rows, key=lambda c: (-int(c["score_bp"]), -int(c["weight_bp"]), c["code"]))
    else:
        best = min(rows, key=lambda c: (int(c["score_bp"]), -int(c["weight_bp"]), c["code"]))
    return str(best["name"])


def outcome(attempt: TestAttempt, evidence: SkillEvidence | None) -> str:
    if evidence is not None and evidence.voided_at is not None:
        return "VOIDED"
    if attempt.terminated_reason in (TerminatedReason.FOCUS_LIMIT, TerminatedReason.ADMIN_VOID):
        return "ENDED_EARLY"
    return "PASSED" if attempt.passed else "NOT_PASSED"


def result_out(
    attempt: TestAttempt,
    bp: AssessmentBlueprint,
    evidence: SkillEvidence | None,
    settings: PlatformSettingsValues,
) -> AssessmentResultOut:
    if attempt.submitted_at is None:  # pragma: no cover - callers pass scored attempts
        raise ValueError("result of an attempt that isn't scored")
    kind = outcome(attempt, evidence)
    passed = kind == "PASSED"
    next_at = (
        None
        if passed or kind == "VOIDED"  # a voided attempt may be retaken at once (§6.7)
        else attempt.submitted_at + timedelta(days=settings.assessment.retake_days)
    )
    return AssessmentResultOut(
        attempt_id=attempt.id,
        label=bp.label,
        outcome=kind,
        passed=passed,
        score=_pct(attempt.overall_bp or 0),
        pass_overall=_pct(int(bp.pass_rule["overall_bp"])),
        competencies=[
            CompetencyScoreOut(
                code=c["code"],
                name=c["name"],
                weight_bp=int(c["weight_bp"]),
                score=_pct(int(c["score_bp"])),
            )
            for c in attempt.breakdown or []
        ],
        strongest=_named(attempt, "strongest"),
        weakest=_named(attempt, "weakest"),
        submitted_at=attempt.submitted_at,
        valid_until=evidence.valid_until if evidence is not None and passed else None,
        next_allowed_at=next_at,
    )


def _blueprint_out(bp: AssessmentBlueprint, extra_seconds: int) -> BlueprintOut:
    rule = bp.pass_rule
    return BlueprintOut(
        label=bp.label,
        competencies=[
            BlueprintCompetencyOut(
                code=c["code"],
                name=c["name"],
                weight_bp=int(c["weight_bp"]),
                question_count=int(c["question_count"]),
                reasons=list(c.get("reasons", [])),
            )
            for c in bp.competencies
        ],
        question_count=bp.question_count,
        time_limit_seconds=bp.time_limit_seconds,
        extra_time_seconds=extra_seconds,
        pass_overall=_pct(int(rule["overall_bp"])),
        floor=_pct(int(rule["floor_bp"])),
        heavy_weight=_pct(int(rule["heavy_weight_bp"])),
    )


async def _extra_seconds(db: AsyncSession, user_id: uuid.UUID, base: int) -> int:
    acc = await repo.accommodation(db, user_id)
    return base * acc.extra_time_pct // 100 if acc is not None else 0


def _valid_pass(e: SkillEvidence, now: datetime) -> bool:
    return bool(
        e.passed and e.voided_at is None and e.valid_until is not None and e.valid_until > now
    )


# --------------------------------------------------------------------------- slot status


@dataclass
class _Eval:
    """Everything the status, the start and the bid gate decide from."""

    status: str
    message: str
    now: datetime
    project: Project
    slot: ProjectSlot
    settings: PlatformSettingsValues
    reason: str | None = None
    blueprint: AssessmentBlueprint | None = None
    extra_seconds: int = 0
    open_attempt: TestAttempt | None = None
    latest: TestAttempt | None = None
    latest_evidence: SkillEvidence | None = None
    passing_evidence: SkillEvidence | None = None
    next_allowed_at: datetime | None = None
    fallback: FallbackOut | None = None


async def _visible_slot(
    ctx: Ctx, project_id: uuid.UUID, slot_id: uuid.UUID
) -> tuple[Project, ProjectSlot]:
    project = await projrepo.get_project(ctx.db, project_id)
    if project is None or project.status == ProjectStatus.DRAFT:
        raise NotFoundError
    slot = next((s for s in await projrepo.load_slots(ctx.db, project_id) if s.id == slot_id), None)
    if slot is None:
        raise NotFoundError
    return project, slot


async def _score_due(ctx: Ctx, attempts: Sequence[TestAttempt]) -> bool:
    """Score the caller's own role attempts whose time ran out (§6.3); True if any was."""
    scored = False
    for a in attempts:
        if a.kind.value == "ROLE" and a.submitted_at is None and ctx.now > a.deadline_at + GRACE:
            await repo.score(ctx.db, a.id, ctx.now)
            await write_audit(
                ctx.db,
                action="role_assessment.score",
                entity_type="test_attempt",
                entity_id=a.id,
                actor_id=ctx.uid,
                actor_role=ctx.principal.role,
                after={"how": "time_up"},
            )
            scored = True
    if scored:
        await ctx.db.commit()
    return scored


def _set(ev: _Eval, status: str, message: str, reason: str | None = None) -> _Eval:
    ev.status, ev.message, ev.reason = status, message, reason
    return ev


async def _gates(ctx: Ctx, ev: _Eval, skill_name: str) -> _Eval | None:
    """§6.2 rules 1–5: bidding open, newcomer rule on, verified, skill on profile, newcomer."""
    project, settings = ev.project, ev.settings
    deadline = project.bidding_deadline
    if project.status != ProjectStatus.BIDDING or (deadline is not None and ctx.now >= deadline):
        return _set(ev, "CLOSED", "Bidding has closed for this project.")
    if not _newcomer_rule_on(settings):
        return _set(ev, "NOT_REQUIRED", "No role assessment is needed in this mode.")
    if ctx.principal.status != "ACTIVE":
        return _set(
            ev,
            "BLOCKED",
            "Verify your phone and email before taking a role assessment.",
            "ACCOUNT_NOT_VERIFIED",
        )
    skills = (await bidrepo.skills_by_developer(ctx.db, [ctx.uid])).get(ctx.uid, set())
    if ev.slot.skill_id not in skills:
        return _set(
            ev,
            "BLOCKED",
            f"Add {skill_name} to your profile to bid for this role.",
            "SKILL_NOT_ON_PROFILE",
        )
    if not (await reputation_read.read_one(ctx.db, ctx.uid, settings)).is_newcomer:
        return _set(ev, "NOT_REQUIRED", "Your completed work speaks for you here.")
    return None


async def _fallback(ctx: Ctx, ev: _Eval, skill_name: str) -> _Eval:
    """Decision 10: no assessment can be served, so the practice result for the skill counts."""
    practice = (await bidrepo.best_evidence_by_developer(ctx.db, [ctx.uid])).get(ctx.uid, {})
    score = practice.get(ev.slot.skill_id)
    mark = ev.settings.newcomer.pass_mark
    ev.fallback = FallbackOut(
        skill_name=skill_name,
        practice_score=int(score * 100) if score is not None else None,
        passes=score is not None and Decimal(str(score)) >= mark,
        pass_mark=int(mark * 100),
    )
    return _set(
        ev,
        "FALLBACK_PRACTICE",
        "A role assessment isn't available for this role yet, so your practice test result "
        f"for {skill_name} is used.",
    )


def _live(attempt: TestAttempt, now: datetime) -> bool:
    grace = GRACE if attempt.kind.value == "ROLE" else timedelta(0)
    return now <= attempt.deadline_at + grace


async def _attempt_states(ctx: Ctx, ev: _Eval, bp: AssessmentBlueprint) -> _Eval:
    """§6.2 rules 7–9 as states: passed, in progress (here or elsewhere), retake locked."""
    ev.extra_seconds = await _extra_seconds(ctx.db, ctx.uid, bp.time_limit_seconds)
    open_attempts = list(await repo.open_attempts(ctx.db, ctx.uid))
    if await _score_due(ctx, open_attempts):
        open_attempts = list(await repo.open_attempts(ctx.db, ctx.uid))
    scored = [a for a in await repo.role_attempts(ctx.db, ctx.uid, bp.id) if a.submitted_at]
    evidence = {e.attempt_id: e for e in await repo.evidence_for(ctx.db, [ctx.uid], [bp.id])}
    if scored:
        ev.latest, ev.latest_evidence = scored[0], evidence.get(scored[0].id)
    passing = next(
        (a for a in scored if (e := evidence.get(a.id)) and _valid_pass(e, ctx.now)), None
    )
    if passing is not None:
        ev.latest, ev.latest_evidence = passing, evidence[passing.id]
        ev.passing_evidence = evidence[passing.id]
        return _set(ev, "PASSED", "You've passed the assessment for this role.")
    live = [a for a in open_attempts if _live(a, ctx.now)]
    if live:
        ev.open_attempt = live[0]
        if live[0].blueprint_id == bp.id:
            return _set(ev, "IN_PROGRESS", "Your assessment for this role is in progress.")
        return _set(ev, "OPEN_ELSEWHERE", "Finish or let your other assessment expire first.")
    counted = [a for a in scored if not (a.id in evidence and evidence[a.id].voided_at)]
    if counted and counted[0].submitted_at is not None:
        allowed = counted[0].submitted_at + timedelta(days=ev.settings.assessment.retake_days)
        if allowed > ctx.now:
            ev.next_allowed_at = allowed
            return _set(ev, "RETAKE_LOCKED", "You can retake this assessment later.")
    return _set(
        ev,
        "REQUIRED",
        "As a new developer on DevSync, you show your competency for this role with a short "
        "assessment.",
    )


async def _evaluate(ctx: Ctx, project: Project, slot: ProjectSlot) -> _Eval:
    """The slot's assessment status for the caller (§8.1), checking §6.2's rules in order."""
    settings = await active_settings(ctx.db)
    ev = _Eval(
        status="REQUIRED", message="", now=ctx.now, project=project, slot=slot, settings=settings
    )
    skill = await ctx.db.get(Skill, slot.skill_id)
    skill_name = skill.name if skill is not None else "this skill"
    stopped = await _gates(ctx, ev, skill_name)
    if stopped is not None:
        return stopped
    ev.blueprint = (await _links(ctx.db, project, [slot])).get(slot.id)
    if ev.blueprint is None or not await available_now(ctx.db, ev.blueprint, settings):
        return await _fallback(ctx, ev, skill_name)
    return await _attempt_states(ctx, ev, ev.blueprint)


def _status_out(ev: _Eval) -> AssessmentStatusOut:
    bp = ev.blueprint
    result = None
    if ev.latest is not None and bp is not None:
        result = result_out(ev.latest, bp, ev.latest_evidence, ev.settings)
    closes_soon = False
    deadline = ev.project.bidding_deadline
    if bp is not None and deadline is not None and ev.status == "REQUIRED":
        span = timedelta(seconds=bp.time_limit_seconds + ev.extra_seconds) + CLOSES_SOON_MARGIN
        closes_soon = deadline < ev.now + span
    return AssessmentStatusOut(
        status=ev.status,
        reason=ev.reason,
        message=ev.message,
        rules_version=RULES_VERSION,
        blueprint=_blueprint_out(bp, ev.extra_seconds)
        if bp is not None
        and bp.status == BlueprintStatus.AVAILABLE
        and ev.status != "FALLBACK_PRACTICE"
        else None,
        attempt_id=ev.open_attempt.id if ev.status == "IN_PROGRESS" and ev.open_attempt else None,
        open_elsewhere=ev.open_attempt.id
        if ev.status == "OPEN_ELSEWHERE" and ev.open_attempt
        else None,
        result=result,
        next_allowed_at=ev.next_allowed_at,
        fallback=ev.fallback,
        bidding_deadline=deadline,
        bidding_closes_soon=closes_soon,
    )


async def slot_status(ctx: Ctx, project_id: uuid.UUID, slot_id: uuid.UUID) -> AssessmentStatusOut:
    authorize(ctx.principal, "assessment.take")
    project, slot = await _visible_slot(ctx, project_id, slot_id)
    return _status_out(await _evaluate(ctx, project, slot))


async def status_for(ctx: Ctx, project: Project, slot: ProjectSlot) -> AssessmentStatusOut | None:
    """The status for a developer's own bid sheet (eligibility preview, bid detail)."""
    if ctx.principal.role != "DEVELOPER":
        return None
    return _status_out(await _evaluate(ctx, project, slot))


async def status_payload(ctx: Ctx, project: Project, slot: ProjectSlot) -> dict[str, Any]:
    """The §8.1 status as JSON, for the bid gate's 409 (the bid sheet renders it directly)."""
    return _status_out(await _evaluate(ctx, project, slot)).model_dump(mode="json")


# ----------------------------------------------------------------------------- attempts


def _token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _check_token(attempt: TestAttempt, token: str | None) -> bytes:
    """Constant-time check of the window token (§6.6); the SQL functions check it again."""
    if not token:
        raise DomainError(code=ErrorCode.ATTEMPT_TOKEN_REQUIRED)
    if len(token) > MAX_TOKEN_LENGTH:
        raise DomainError(code=ErrorCode.ATTEMPT_TOKEN_INVALID)
    given = _token_hash(token)
    stored = attempt.attempt_token_hash or b""
    if hmac.compare_digest(given, stored):
        return given
    if any(hmac.compare_digest(given, old) for old in attempt.retired_token_hashes or []):
        raise DomainError(code=ErrorCode.ATTEMPT_MOVED)
    raise DomainError(code=ErrorCode.ATTEMPT_TOKEN_INVALID)


def _db_error(exc: DBAPIError) -> DomainError:
    code, extra = repo.domain_code(exc)
    if code is not None and code in ErrorCode.__members__:
        return DomainError(code=ErrorCode(code), extra=extra)
    state = repo.sqlstate(exc)
    if state == "P0002":
        return NotFoundError()
    if state == "23514":
        return DomainError(code=ErrorCode.VALIDATION_ERROR, fields={"body": "not accepted"})
    raise exc


async def _own(ctx: Ctx, attempt_id: uuid.UUID) -> TestAttempt:
    attempt = await repo.get_attempt(ctx.db, attempt_id)
    if attempt is None:
        raise NotFoundError
    authorize(ctx.principal, "assessment.take", attempt)  # another developer's → 404
    return attempt


async def _blueprint(ctx: Ctx, attempt: TestAttempt) -> AssessmentBlueprint:
    bp = await repo.get_blueprint(ctx.db, attempt.blueprint_id)  # type: ignore[arg-type]
    if bp is None:  # pragma: no cover - FK
        raise NotFoundError
    return bp


async def _expire_if_due(ctx: Ctx, attempt: TestAttempt) -> TestAttempt:
    if attempt.submitted_at is None and ctx.now > attempt.deadline_at + GRACE:
        await _score_due(ctx, [attempt])
        attempt = await _own(ctx, attempt.id)
    return attempt


async def _result(ctx: Ctx, attempt: TestAttempt) -> AssessmentResultOut:
    settings = await active_settings(ctx.db)
    bp = await _blueprint(ctx, attempt)
    rows = [
        e
        for e in await repo.evidence_for(ctx.db, [attempt.user_id], [bp.id])
        if e.attempt_id == attempt.id
    ]
    evidence = rows[0] if rows else None
    return result_out(attempt, bp, evidence, settings)


def _closed(result: AssessmentResultOut, code: ErrorCode = ErrorCode.ATTEMPT_CLOSED) -> DomainError:
    return DomainError(code=code, extra={"result": result.model_dump(mode="json")})


def _question_out(q: repo.CurrentQuestion) -> QuestionOut:
    return QuestionOut(
        id=q.question_id,
        index=q.index,
        total=q.total,
        text=q.text,
        code_snippet=q.code_snippet,
        options=q.options,
        competency=q.competency_name,
    )


async def _state(ctx: Ctx, attempt: TestAttempt, token_hash: bytes | None) -> AttemptStateOut:
    bp = await _blueprint(ctx, attempt)
    question = None
    result = None
    if attempt.submitted_at is None and token_hash is not None:
        current = await repo.current_question(ctx.db, attempt.id, token_hash)
        question = _question_out(current) if current is not None else None
    if attempt.submitted_at is not None:
        result = await _result(ctx, attempt)
    return AttemptStateOut(
        id=attempt.id,
        label=bp.label,
        state="SCORED" if attempt.submitted_at is not None else "OPEN",
        current_index=attempt.current_index,
        total=len(attempt.question_ids),
        started_at=attempt.started_at,
        deadline_at=attempt.deadline_at,
        server_now=ctx.now,
        focus_leaves=attempt.focus_leaves,
        leave_limit=attempt.leave_limit or 2,
        question=question,
        result=result,
    )


async def _audit(ctx: Ctx, action: str, attempt_id: uuid.UUID, **after: object) -> None:
    await write_audit(
        ctx.db,
        action=action,
        entity_type="test_attempt",
        entity_id=attempt_id,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        after=dict(after) or None,
    )


async def _issue_token(ctx: Ctx, attempt_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    try:
        status = await repo.rotate_token(ctx.db, attempt_id, _token_hash(token), ctx.now)
    except DBAPIError as exc:
        await ctx.db.rollback()
        raise _db_error(exc) from None
    if status != "OK":  # closed meanwhile, or the time ran out (scored by the function)
        await ctx.db.commit()
        raise _closed(await _result(ctx, await _own(ctx, attempt_id)))
    return token


async def resume(ctx: Ctx, attempt_id: uuid.UUID) -> StartedOut:
    """A new window token for an open attempt; the old window gets ATTEMPT_MOVED (§6.6)."""
    attempt = await _expire_if_due(ctx, await _own(ctx, attempt_id))
    if attempt.submitted_at is not None:
        raise _closed(await _result(ctx, attempt))
    token = await _issue_token(ctx, attempt_id)
    await _audit(ctx, "role_assessment.resume", attempt_id)
    await ctx.db.commit()
    attempt = await _own(ctx, attempt_id)
    state = await _state(ctx, attempt, _token_hash(token))
    return StartedOut(**state.model_dump(), attempt_token=token)


_START_ERRORS = {
    "NOT_REQUIRED": ErrorCode.NOT_REQUIRED,
    "CLOSED": ErrorCode.BIDDING_CLOSED,
    "FALLBACK_PRACTICE": ErrorCode.BLUEPRINT_UNAVAILABLE,
    "PASSED": ErrorCode.ALREADY_PASSED,
    "OPEN_ELSEWHERE": ErrorCode.ATTEMPT_OPEN,
    "RETAKE_LOCKED": ErrorCode.RETAKE_LOCKED,
}


async def start(
    ctx: Ctx,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
    body: StartIn,
    idempotency_key: str | None = None,
) -> tuple[StartedOut, bool]:
    """Start (or, for the same role, resume) an attempt. Returns (attempt, created).

    The rules of §6.2 are checked in order; 7–9 again inside `start_role_attempt` under the
    per-developer lock. A repeated Idempotency-Key gets the same attempt with a fresh window token:
    the token is stored only hashed, so it can't be replayed from the idempotency record.
    """
    authorize(ctx.principal, "assessment.take")
    project, slot = await _visible_slot(ctx, project_id, slot_id)
    key = idempotency.parse_key(idempotency_key) if idempotency_key is not None else None
    if key is not None:
        fingerprint = idempotency.request_fingerprint(
            "POST",
            f"/projects/{project_id}/slots/{slot_id}/assessment/attempts",
            body.model_dump(mode="json"),
        )
        stored = await idempotency.begin(
            ctx.db, user_id=ctx.uid, key=key, fingerprint=fingerprint, now=ctx.now
        )
        if stored is not None:
            return await resume(ctx, uuid.UUID(str(stored.body["attempt_id"]))), False
    ev = await _evaluate(ctx, project, slot)
    if ev.status == "IN_PROGRESS" and ev.open_attempt is not None:
        return await resume(ctx, ev.open_attempt.id), False
    if ev.status == "BLOCKED":
        code = (
            ErrorCode.ACCOUNT_NOT_VERIFIED
            if ev.reason == "ACCOUNT_NOT_VERIFIED"
            else ErrorCode.SKILL_NOT_ON_PROFILE
        )
        raise DomainError(code=code, extra={"assessment": _status_out(ev).model_dump(mode="json")})
    if ev.status in _START_ERRORS:
        raise DomainError(
            ev.message,
            code=_START_ERRORS[ev.status],
            extra={"assessment": _status_out(ev).model_dump(mode="json")},
        )
    if not body.consent or body.rules_version != RULES_VERSION:
        raise DomainError(code=ErrorCode.CONSENT_REQUIRED, extra={"rules_version": RULES_VERSION})
    bp = ev.blueprint
    if bp is None:  # pragma: no cover - REQUIRED always has a blueprint
        raise DomainError(code=ErrorCode.BLUEPRINT_UNAVAILABLE)
    settings = ev.settings
    seed = secrets.randbits(SEED_BITS)
    recent = await repo.recent_questions(ctx.db, ctx.now - RECENT_WINDOW)
    selection = await _select(ctx.db, bp, settings, recent, seed)
    if selection is None:
        raise DomainError(code=ErrorCode.BLUEPRINT_UNAVAILABLE)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    a = settings.assessment
    try:
        attempt_id, _ = await repo.start(
            ctx.db,
            blueprint_id=bp.id,
            question_ids=selection.question_ids,
            now=ctx.now,
            seed=seed,
            project_id=project.id,
            slot_id=slot.id,
            token_hash=_token_hash(token),
            extra_time=ev.extra_seconds,
            rules_version=RULES_VERSION,
            retake_days=a.retake_days,
            leave_limit=a.leave_limit,
            validity_days=a.validity_days,
            reused_seen=selection.reused_seen,
            min_review=min_review(settings),
        )
    except DBAPIError as exc:
        await ctx.db.rollback()
        db_code, extra = repo.domain_code(exc)
        if db_code == "ATTEMPT_OPEN" and extra.get("blueprint_id") == str(bp.id):
            return await resume(ctx, uuid.UUID(extra["attempt_id"])), False  # a parallel start won
        raise _db_error(exc) from None
    await _audit(
        ctx,
        "role_assessment.start",
        attempt_id,
        blueprint=bp.fingerprint[:12],
        project_id=str(project.id),
        slot_id=str(slot.id),
        reused_seen=selection.reused_seen,
    )
    if key is not None:
        await idempotency.complete(
            ctx.db, user_id=ctx.uid, key=key, status_code=201, body={"attempt_id": str(attempt_id)}
        )
    await ctx.db.commit()
    attempt = await _own(ctx, attempt_id)
    state = await _state(ctx, attempt, _token_hash(token))
    return StartedOut(**state.model_dump(), attempt_token=token), True


async def get(ctx: Ctx, attempt_id: uuid.UUID, token: str | None) -> AttemptStateOut:
    """The attempt's state; the current question only with a valid window token (§9)."""
    attempt = await _expire_if_due(ctx, await _own(ctx, attempt_id))
    token_hash = None
    if attempt.submitted_at is None and token:
        token_hash = _check_token(attempt, token)
    return await _state(ctx, attempt, token_hash)


async def answer(ctx: Ctx, attempt_id: uuid.UUID, body: AnswerIn, token: str | None) -> AnswerOut:
    attempt = await _own(ctx, attempt_id)
    if attempt.submitted_at is not None:
        raise _closed(await _result(ctx, attempt))
    token_hash = _check_token(attempt, token)
    try:
        status, index = await repo.record_answer(
            ctx.db,
            attempt_id,
            question_id=body.question_id,
            choice=body.choice,
            now=ctx.now,
            token_hash=token_hash,
        )
    except DBAPIError as exc:
        await ctx.db.rollback()
        raise _db_error(exc) from None
    if status == "EXPIRED":
        await _audit(ctx, "role_assessment.score", attempt_id, how="time_up")
        await ctx.db.commit()
        raise _closed(await _result(ctx, await _own(ctx, attempt_id)), ErrorCode.DEADLINE_PASSED)
    if status == "CLOSED":
        await ctx.db.rollback()
        raise _closed(await _result(ctx, await _own(ctx, attempt_id)))
    if status != "DUPLICATE":
        await _audit(ctx, "role_assessment.answer", attempt_id, index=index - 1)  # no choice logged
    if status == "SCORED":
        await _audit(ctx, "role_assessment.score", attempt_id, how="completed")
    await ctx.db.commit()
    attempt = await _own(ctx, attempt_id)
    total = len(attempt.question_ids)
    if status == "SCORED":
        return AnswerOut(
            status="SCORED", current_index=index, total=total, result=await _result(ctx, attempt)
        )
    current = await repo.current_question(ctx.db, attempt_id, token_hash)
    return AnswerOut(
        status="NEXT",
        current_index=attempt.current_index,
        total=total,
        question=_question_out(current) if current is not None else None,
    )


async def finish(ctx: Ctx, attempt_id: uuid.UUID, token: str | None) -> AssessmentResultOut:
    """End early: the questions not yet answered count as wrong (§6.4)."""
    attempt = await _own(ctx, attempt_id)
    if attempt.submitted_at is not None:
        raise _closed(await _result(ctx, attempt))
    token_hash = _check_token(attempt, token)
    try:
        status = await repo.finish(ctx.db, attempt_id, ctx.now, token_hash)
    except DBAPIError as exc:
        await ctx.db.rollback()
        raise _db_error(exc) from None
    if status == "SCORED":
        await _audit(ctx, "role_assessment.score", attempt_id, how="finished_early")
    await ctx.db.commit()
    return await _result(ctx, await _own(ctx, attempt_id))


def _client_time(value: datetime | None, now: datetime) -> datetime | None:
    if value is None or value.tzinfo is None or abs(value - now) > CLIENT_CLOCK_WINDOW:
        return None
    return value


async def focus_event(
    ctx: Ctx, attempt_id: uuid.UUID, body: FocusEventIn, token: str | None
) -> FocusEventOut:
    """One counted leave (§7.4): a warning first, then the attempt ends (scored, never a pass)."""
    attempt = await _own(ctx, attempt_id)
    limit = attempt.leave_limit or 2
    if attempt.submitted_at is not None:
        return FocusEventOut(
            status="CLOSED",
            focus_leaves=attempt.focus_leaves,
            leave_limit=limit,
            result=await _result(ctx, attempt),
        )
    token_hash = _check_token(attempt, token)
    try:
        status, leaves = await repo.focus_event(
            ctx.db,
            attempt_id,
            seq=body.seq,
            kind=body.type,
            now=ctx.now,
            client_at=_client_time(body.client_at, ctx.now),
            fullscreen_supported=body.fullscreen_supported,
            token_hash=token_hash,
        )
    except DBAPIError as exc:
        await ctx.db.rollback()
        raise _db_error(exc) from None
    if status in ("WARNING", "TERMINATED"):
        await _audit(ctx, "role_assessment.focus_leave", attempt_id, seq=body.seq, type=body.type)
    if status == "TERMINATED":
        await _audit(ctx, "role_assessment.terminate", attempt_id, focus_leaves=leaves)
    if status == "EXPIRED":
        await _audit(ctx, "role_assessment.score", attempt_id, how="time_up")
    await ctx.db.commit()
    attempt = await _own(ctx, attempt_id)
    if attempt.submitted_at is not None:
        kind = "TERMINATED" if status == "TERMINATED" else "CLOSED"
        return FocusEventOut(
            status=kind,
            focus_leaves=attempt.focus_leaves,
            leave_limit=limit,
            result=await _result(ctx, attempt),
        )
    return FocusEventOut(status="WARNING", focus_leaves=leaves, leave_limit=limit)


async def heartbeat(ctx: Ctx, attempt_id: uuid.UUID, token: str | None) -> HeartbeatOut:
    attempt = await _own(ctx, attempt_id)
    if attempt.submitted_at is not None:
        raise _closed(await _result(ctx, attempt))
    token_hash = _check_token(attempt, token)
    try:
        status = await repo.heartbeat(ctx.db, attempt_id, ctx.now, token_hash)
    except DBAPIError as exc:
        await ctx.db.rollback()
        raise _db_error(exc) from None
    if status == "EXPIRED":
        await _audit(ctx, "role_assessment.score", attempt_id, how="time_up")
    await ctx.db.commit()
    if status != "OK":
        raise _closed(await _result(ctx, await _own(ctx, attempt_id)))
    return HeartbeatOut(server_now=ctx.now, deadline_at=attempt.deadline_at)


async def result(ctx: Ctx, attempt_id: uuid.UUID) -> AssessmentResultOut:
    attempt = await _expire_if_due(ctx, await _own(ctx, attempt_id))
    if attempt.submitted_at is None:
        raise DomainError(
            "This assessment is still running.",
            code=ErrorCode.INVALID_STATE,
            extra={"current_state": "OPEN", "allowed_actions": ["answer", "finish"]},
        )
    return await _result(ctx, attempt)


async def history(ctx: Ctx) -> list[HistoryItemOut]:
    authorize(ctx.principal, "assessment.take")
    attempts = [a for a in await repo.role_attempts(ctx.db, ctx.uid) if a.submitted_at is not None]
    bps = await repo.blueprints(ctx.db, list({a.blueprint_id for a in attempts if a.blueprint_id}))
    evidence = await repo.evidence_for(ctx.db, [ctx.uid], list(bps))
    by_attempt = {e.attempt_id: e for e in evidence}
    out = []
    for a in attempts:
        bp = bps[a.blueprint_id]  # type: ignore[index]
        e = by_attempt.get(a.id)
        kind = outcome(a, e)
        out.append(
            HistoryItemOut(
                attempt_id=a.id,
                label=bp.label,
                outcome=kind,
                score=_pct(a.overall_bp or 0),
                passed=kind == "PASSED",
                started_at=a.started_at,
                submitted_at=a.submitted_at,
                valid_until=e.valid_until if e is not None and kind == "PASSED" else None,
            )
        )
    return out


async def score_expired(db: AsyncSession, now: datetime, limit: int = 200) -> int:
    """Worker job (SYSTEM): score role attempts whose time (+ grace) ran out (§6.3)."""
    done = 0
    for attempt_id in await repo.expired_open(db, now - GRACE, limit):
        try:
            if await repo.score(db, attempt_id, now) == "SCORED":
                await write_audit(
                    db,
                    action="role_assessment.score",
                    entity_type="test_attempt",
                    entity_id=attempt_id,
                    actor_role="SYSTEM",
                    after={"how": "time_up"},
                )
                done += 1
            await db.commit()
        except DBAPIError:  # scored by its owner's request meanwhile
            await db.rollback()
    return done


# -------------------------------------------------------------------- bidding integration


@dataclass(frozen=True)
class AssessmentLine:
    """A newcomer's role result as the bids views describe it (§8.2, §8.5)."""

    score: int
    pass_overall: int
    passed: bool
    ended_early: bool
    voided: bool
    expired: bool
    floor_miss: tuple[str, int, int] | None  # (competency, score, floor)
    strongest: str | None
    weakest: str | None
    taken_at: datetime


@dataclass(frozen=True)
class SlotEvidence:
    """The newcomer evidence for one bid: a role result (or none) or a practice score."""

    kind: Kind
    score: float | None
    passed: bool | None
    evidence_id: uuid.UUID | None = None
    line: AssessmentLine | None = None


def _line(
    e: SkillEvidence, a: TestAttempt | None, bp: AssessmentBlueprint, now: datetime
) -> AssessmentLine:
    rule = bp.pass_rule
    floor_miss = None
    for c in (a.breakdown if a is not None else None) or []:
        if int(c["weight_bp"]) >= int(rule["heavy_weight_bp"]) and int(c["score_bp"]) < int(
            rule["floor_bp"]
        ):
            floor_miss = (str(c["name"]), _pct(int(c["score_bp"])), _pct(int(rule["floor_bp"])))
            break
    ended = a is not None and a.terminated_reason in (
        TerminatedReason.FOCUS_LIMIT,
        TerminatedReason.ADMIN_VOID,
    )
    return AssessmentLine(
        score=_pct(a.overall_bp or 0) if a is not None else int(e.score * 100),
        pass_overall=_pct(int(rule["overall_bp"])),
        passed=bool(e.passed) and e.voided_at is None,
        ended_early=ended,
        voided=e.voided_at is not None,
        expired=bool(e.passed) and e.valid_until is not None and e.valid_until <= now,
        floor_miss=floor_miss,
        strongest=_named(a, "strongest") if a is not None else None,
        weakest=_named(a, "weakest") if a is not None else None,
        taken_at=e.at,
    )


async def newcomer_evidence(
    db: AsyncSession,
    *,
    project: Project,
    slots: Sequence[ProjectSlot],
    items: Sequence[tuple[uuid.UUID, uuid.UUID, uuid.UUID | None]],
    settings: PlatformSettingsValues,
    now: datetime,
) -> dict[tuple[uuid.UUID, uuid.UUID], SlotEvidence]:
    """Evidence for each (developer, slot, linked evidence id) of a project's newcomer bids.

    Where the slot's assessment can be served, the evidence is the role result: the one linked
    to the bid (kept even after it expires, unless voided, §8.3), otherwise a valid pass for the
    blueprint, otherwise the latest result (failed, ended early, voided) or none. Where it can't
    (Decision 10), the developer's best practice score for the slot's skill.
    """
    out: dict[tuple[uuid.UUID, uuid.UUID], SlotEvidence] = {}
    if not items:
        return out
    links = await _links(db, project, slots)
    usable = {sid: bp for sid, bp in links.items() if await available_now(db, bp, settings)}
    devs = list({d for d, _, _ in items})
    practice = await bidrepo.best_evidence_by_developer(db, devs)
    slot_skill = {s.id: s.skill_id for s in slots}
    role_items = [(d, s, linked) for d, s, linked in items if s in usable]
    evidence = await repo.evidence_for(db, devs, list({usable[s].id for _, s, _ in role_items}))
    linked_rows = await repo.evidence_by_ids(db, [linked for _, _, linked in items if linked])
    attempts = await repo.attempts_by_ids(
        db, [e.attempt_id for e in [*evidence, *linked_rows.values()] if e.attempt_id]
    )
    for dev, slot_id, linked in items:
        bp = usable.get(slot_id)
        if bp is None:
            score = practice.get(dev, {}).get(slot_skill.get(slot_id))  # type: ignore[arg-type]
            out[(dev, slot_id)] = SlotEvidence("PRACTICE", score, None)
            continue
        mine = [e for e in evidence if e.user_id == dev and e.blueprint_id == bp.id]
        chosen = linked_rows.get(linked) if linked else None
        if chosen is not None and (chosen.voided_at is not None or chosen.blueprint_id != bp.id):
            chosen = next((e for e in mine if _valid_pass(e, now)), chosen)
        if chosen is None:
            chosen = next((e for e in mine if _valid_pass(e, now)), None)
        if chosen is None:
            latest = mine[0] if mine else None
            if latest is None or (latest.passed and latest.voided_at is None):
                # nothing, or a pass that has expired: no evidence for a new bid
                out[(dev, slot_id)] = SlotEvidence(
                    "ROLE",
                    None,
                    None,
                    line=_line(latest, attempts.get(latest.attempt_id or uuid.UUID(int=0)), bp, now)
                    if latest
                    else None,
                )
                continue
            chosen = latest
        line = _line(chosen, attempts.get(chosen.attempt_id), bp, now)  # type: ignore[arg-type]
        passed = line.passed
        out[(dev, slot_id)] = SlotEvidence(
            "ROLE", float(chosen.score), passed, evidence_id=chosen.id, line=line
        )
    return out


async def require_for_bid(ctx: Ctx, project: Project, slot: ProjectSlot) -> uuid.UUID | None:
    """The evidence a newcomer's new (or moved) bid relies on; 409 ROLE_ASSESSMENT_REQUIRED
    without a valid pass (or, where no assessment exists, a passing practice score) (§8.3)."""
    settings = await active_settings(ctx.db)
    if not _newcomer_rule_on(settings):
        return None
    rep = await reputation_read.read_one(ctx.db, ctx.uid, settings)
    if not rep.is_newcomer:
        return None
    slots = list(await projrepo.load_slots(ctx.db, project.id))
    evidence = await newcomer_evidence(
        ctx.db,
        project=project,
        slots=slots,
        items=[(ctx.uid, slot.id, None)],
        settings=settings,
        now=ctx.now,
    )
    found = evidence[(ctx.uid, slot.id)]
    mark = float(settings.newcomer.pass_mark)
    if found.kind == "ROLE" and found.passed and found.evidence_id is not None:
        return found.evidence_id
    if found.kind == "PRACTICE" and found.score is not None and found.score >= mark - 1e-9:
        return None
    raise DomainError(
        code=ErrorCode.ROLE_ASSESSMENT_REQUIRED,
        extra={"assessment": await status_payload(ctx, project, slot)},
    )
