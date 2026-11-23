"""Team formation (spec §9.2–§9.8, §10.2 Formation, §14.13 row 7; DECISIONS D105–D110).

Start: the project's client starts a run on a FORMING project. Algorithm 1 is re-run through
`bids.evaluate` with the run's minimum standards and the preset's advancement choice; its
per-slot shortlist becomes the candidate snapshot, frozen with the parameters and a
server-generated seed (D106). The run and its job are written in a SYSTEM session after the
caller was authorised (D50 pattern) and the `formation.run` job is queued. One run at a time per
project, 10 starts an hour per client (`ratelimit.formation_run`), and an Idempotency-Key replays
the first answer.

Confirm: the client confirms a finished run; the project goes FORMING → TEAM_PENDING, the team's
bids become SELECTED and every other standing bid NOT_SELECTED, the team, its members, their
(not yet sent, D108) invitations and tentative availability reservations are created, the
non-selected bidders are told, and the explanations job is queued.

Reading: the client reads their runs; an admin reads every run and may re-run one to verify it
reproduces (step-up required). A bidder reads why their own bid was not selected — never anything
about the other bids.
"""

from __future__ import annotations

import base64
import binascii
import math
import secrets
import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms import fitness as fit
from app.algorithms.cpm import CpmError, MilestoneInput, compute_cpm
from app.algorithms.filtering import Advancement
from app.core import idempotency, task_queue
from app.core.audit import write_audit
from app.core.authz import authorize
from app.core.errors import DomainError, ErrorCode, InvalidStateTransition, NotFoundError
from app.core.logging import get_logger
from app.db.context import DbContext
from app.db.session import open_session
from app.models.bidding import AvailabilityReservation, Bid, BidStatus, ReservationStatus
from app.models.formation import (
    BidExplanation,
    FormationRun,
    Invitation,
    RunStatus,
    Team,
    TeamMember,
)
from app.models.foundation import Job, JobStatus
from app.models.identity import User
from app.models.projects import Project, ProjectStatus
from app.repositories import projects as projrepo
from app.schemas.formation import (
    AdminRunOut,
    BidExplanationOut,
    ConfirmOut,
    FormationRunAccepted,
    FormationRunCreate,
    FormationRunOut,
    FormationRunSummary,
    RunParams,
    RunResult,
    SlotComparison,
    WeightsOut,
)
from app.schemas.platform_settings import PlatformSettingsValues
from app.services import bids as bids_svc
from app.services import platform_settings
from app.services.context import Ctx
from app.services.notifications import notify

log = get_logger(__name__)

JOB_TYPE = "formation.run"
EXPLAIN_JOB_TYPE = "formation.explanations"
VERIFY_JOB_TYPE = "formation.verify"
SEED_BITS = 31
# A run still QUEUED/RUNNING after this belongs to a dead worker (its RQ timeout is 60 s), so it
# no longer blocks a new run.
STALE_RUN = timedelta(minutes=5)
FINISHED = (RunStatus.SUCCEEDED, RunStatus.TIMED_OUT)
ADVANCEMENT = {
    "quality": Advancement.P,
    "balanced": Advancement.C,
    "fast": Advancement.T,
    "budget": Advancement.C_COST,
}
HINTS = {
    "comp": "Completing projects in more domains or passing skill tests raises your competency.",
    "team": "Ratings from teammates and helping with blockers raise your teamwork score.",
    "time": "A shorter delivery time would have helped most.",
    "cost": "A lower price would have helped most.",
}
LIST_LIMIT = 50


# ------------------------------------------------------------------------------- helpers


def _r(value: float, places: int = 3) -> float:
    """Half-up rounding for stored and shown scores (D105)."""
    q = Decimal(1).scaleb(-places)
    return float(Decimal(repr(value)).quantize(q, rounding="ROUND_HALF_UP"))


def _weights(body: FormationRunCreate) -> fit.Weights:
    if body.weights is None:
        return fit.preset_weights(body.preset)
    w = body.weights
    total = w.competency + w.teamwork + w.time + w.cost
    return fit.Weights(
        float(w.competency / total),
        float(w.teamwork / total),
        float(w.time / total),
        float(w.cost / total),
    )


async def _own_project(ctx: Ctx, project_id: uuid.UUID) -> Project:
    project = await projrepo.get_project(ctx.db, project_id)
    if project is None or project.client_id != ctx.uid:
        raise NotFoundError
    return project


async def _critical_skills(db: AsyncSession, project_id: uuid.UUID) -> frozenset[str]:
    """Skills a milestone on a critical path needs (for the §9.7 risk chips)."""
    milestones = list(await projrepo.load_milestones(db, project_id))
    if not milestones:
        return frozenset()
    deps = list(await projrepo.load_dependencies(db, project_id))
    preds: dict[uuid.UUID, list[str]] = {m.id: [] for m in milestones}
    for d in deps:
        preds.setdefault(d.successor_id, []).append(str(d.predecessor_id))
    inputs = [MilestoneInput(str(m.id), m.duration_days, tuple(preds[m.id])) for m in milestones]
    try:
        cpm = compute_cpm(inputs)
    except CpmError:
        return frozenset()
    critical = [m.id for m in milestones if cpm.nodes[str(m.id)].critical]
    skills = await projrepo.load_milestone_skills(db, critical)
    return frozenset(str(s) for ids in skills.values() for s in ids)


def _settings_params(settings: PlatformSettingsValues) -> dict[str, Any]:
    pso, exact = settings.pso, settings.exact
    return {
        "pso": {
            "particles": pso.particles,
            "max_iter": pso.max_iter,
            "z1": float(pso.z1),
            "z2": float(pso.z2),
            "inertia": float(pso.inertia),
            "v_max": float(pso.v_max),
            "bounds": [float(pso.bounds[0]), float(pso.bounds[1])],
            "early_stop_iters": pso.early_stop_iters,
            "timeout_seconds": pso.timeout_seconds,
        },
        "exact": {
            "max_candidates": exact.max_candidates,
            "max_combinations": exact.max_combinations,
        },
        "include_performance": settings.fitness.include_performance,
        "use_skill_competency": settings.fitness.use_skill_competency,
        "mode": settings.algorithm.mode,
    }


# --------------------------------------------------------------------------------- start


async def build_snapshot(
    db: AsyncSession,
    today: date,
    project: Project,
    settings: PlatformSettingsValues,
    body: FormationRunCreate,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(candidate snapshot, params) for a new run: Algorithm 1 under the run's standards.
    `db` is a SYSTEM session: eligibility needs each bidder's skills and evidence, which the
    client can't read; the caller was already confirmed as the project's owner (D50)."""
    slots = list(await projrepo.load_slots(db, project.id))
    terms = bids_svc.project_terms(project, slots, settings)
    floor_p, floor_c = bids_svc.threshold_floor(settings)
    p0 = float(body.min_performance) if body.min_performance is not None else terms.p0
    c0 = float(body.min_competency) if body.min_competency is not None else terms.c0
    if p0 < floor_p or c0 < floor_c:
        raise DomainError(
            "The minimum standards can't go below the platform floor.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"min_performance": f"at least {floor_p:.2f}",
                    "min_competency": f"at least {floor_c:.2f}"},
        )  # fmt: skip
    terms = bids_svc.Terms(p0=p0, c0=c0, budget_paisa=terms.budget_paisa,
                           slot_counts=terms.slot_counts)  # fmt: skip
    ev = await bids_svc.evaluate(db, project, settings, today, terms,
                                 advancement=ADVANCEMENT[body.preset])  # fmt: skip
    by_id = {str(b.id): b for b in ev.bids}
    inputs = {i.bid_id: i for i in ev.inputs}
    shortlisted = [bid_id for ids in ev.result.shortlisted.values() for bid_id in ids]
    names = dict(
        (await db.execute(
            select(User.id, User.display_name).where(
                User.id.in_([by_id[b].developer_id for b in shortlisted])
            )
        )).tuples().all()
    )  # fmt: skip
    slot_by_id = {str(s.id): s for s in ev.slots}
    candidates: list[dict[str, Any]] = []
    for bid_id in shortlisted:
        bid, inp = by_id[bid_id], inputs[bid_id]
        rep = ev.reps[bid.developer_id]
        competency = inp.c
        if settings.fitness.use_skill_competency and inp.skill_evidence_score is not None:
            competency = inp.skill_evidence_score
        candidates.append({
            "bid_id": bid_id,
            "developer_id": str(bid.developer_id),
            "developer_name": names.get(bid.developer_id, "Developer"),
            "slot_id": inp.slot_id,
            "slot_label": ev.slot_name(slot_by_id.get(inp.slot_id)),
            "competency": competency,
            "teamwork": rep.xm,
            "performance": inp.p,
            "days": bid.days_needed,
            "price_paisa": bid.price_paisa,
            "hours_per_week": bid.hours_per_week_committed,
            "newcomer": inp.is_newcomer,
            "skills": [inp.skill_id],
        })  # fmt: skip
    newcomers_available = sum(c["newcomer"] for c in candidates)
    k = body.min_newcomers
    if k is None:
        k = min(settings.fairness.default_min_newcomers, 1) if newcomers_available else 0
    weights = _weights(body)
    snapshot = {
        "candidates": candidates,
        "slots": {str(s): n for s, n in ev.terms.slot_counts.items()},
        "required_skills": sorted({c["skills"][0] for c in candidates}),
        "critical_skills": sorted(await _critical_skills(db, project.id)),
        "deadline_days": project.deadline_days,
        "budget_after_fee_paisa": ev.proj.budget_after_fee_paisa,
        "not_shortlisted": list(ev.result.not_shortlisted),
        "rejected": [[bid_id, reason.value] for bid_id, reason in ev.result.rejected],
        "relaxations": [{"step": r.step, "p0": r.p0, "c0": r.c0} for r in ev.result.relaxations],
        "eligible": len(ev.result.eligible),
        "too_few": ev.result.too_few,
    }
    params = {
        "preset": body.preset,
        "weights": {"competency": weights.competency, "teamwork": weights.teamwork,
                    "time": weights.time, "cost": weights.cost},
        "min_newcomers": k,
        "min_performance": p0,
        "min_competency": c0,
        **_settings_params(settings),
    }  # fmt: skip
    return snapshot, params


async def start_run(
    ctx: Ctx,
    project_id: uuid.UUID,
    body: FormationRunCreate,
    idempotency_key: str | None = None,
) -> FormationRunAccepted:
    """Queue a formation run for the client's own FORMING project (202)."""
    authorize(ctx.principal, "formation.run")
    project = await _own_project(ctx, project_id)
    key = idempotency.parse_key(idempotency_key) if idempotency_key is not None else None
    if key is not None:
        fingerprint = idempotency.request_fingerprint(
            "POST", f"/projects/{project_id}/formation-runs", body.model_dump(mode="json")
        )
        stored = await idempotency.begin(
            ctx.db, user_id=ctx.uid, key=key, fingerprint=fingerprint, now=ctx.now
        )
        if stored is not None:
            return FormationRunAccepted.model_validate(stored.body)
    if project.status != ProjectStatus.FORMING:
        message = None
        if project.status == ProjectStatus.BIDDING and bids_svc.bidding_closed(project, ctx.now):
            message = "Bidding has just closed and the bids are being checked. Try again shortly."
        raise InvalidStateTransition(project.status.value, [], message)
    settings_version, settings = await platform_settings.get_active(ctx.db)
    async with open_session(DbContext.system(), job=True) as sysdb:
        snapshot, params = await build_snapshot(sysdb, ctx.now.date(), project, settings, body)
    if not snapshot["candidates"]:
        raise DomainError("There are no eligible bids to form a team from.",
                          code=ErrorCode.INVALID_STATE)  # fmt: skip
    seed = secrets.randbits(SEED_BITS)
    async with open_session(DbContext.system(), job=True) as db:
        # One run at a time per project: the project row is the lock.
        await db.scalar(select(Project.id).where(Project.id == project.id).with_for_update())
        busy = await db.scalar(
            select(func.count()).select_from(FormationRun).where(
                FormationRun.project_id == project.id,
                FormationRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
                FormationRun.created_at > ctx.now - STALE_RUN,
            )
        )  # fmt: skip
        if busy:
            raise DomainError("A team formation run is already in progress for this project.",
                              code=ErrorCode.LIMIT_REACHED)  # fmt: skip
        job = Job(type=JOB_TYPE, status=JobStatus.QUEUED, progress=0, requested_by=ctx.uid)
        db.add(job)
        await db.flush()
        run = FormationRun(project_id=project.id, requested_by=ctx.uid,
                           settings_version=settings_version, seed=seed, params=params,
                           candidate_snapshot=snapshot, job_id=job.id)  # fmt: skip
        db.add(run)
        await db.flush()
        job.result_ref = f"formation_run:{run.id}"
        await write_audit(db, action="formation.run_started", entity_type="formation_run",
                          entity_id=run.id, actor_id=ctx.uid, actor_role=ctx.principal.role,
                          after={"project_id": str(project.id), "preset": body.preset,
                                 "min_newcomers": params["min_newcomers"],
                                 "candidates": len(snapshot["candidates"])})  # fmt: skip
        await db.commit()
        run_id, job_id = run.id, job.id
    accepted = FormationRunAccepted(run_id=run_id, job_id=job_id, status=RunStatus.QUEUED,
                                    progress=0)  # fmt: skip
    if key is not None:
        await idempotency.complete(ctx.db, user_id=ctx.uid, key=key, status_code=202,
                                   body=accepted.model_dump(mode="json"))  # fmt: skip
        await ctx.db.commit()
    try:
        task_queue.enqueue(JOB_TYPE, str(run_id))
    except Exception:
        log.exception("formation_enqueue_failed", run_id=str(run_id))
        await mark_failed(run_id, job_id, "ENQUEUE_FAILED")
        raise DomainError(code=ErrorCode.DEPENDENCY_UNAVAILABLE) from None
    return accepted


async def mark_failed(run_id: uuid.UUID, job_id: uuid.UUID | None, code: str) -> None:
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(update(FormationRun).where(FormationRun.id == run_id)
                         .values(status=RunStatus.FAILED, error_code=code))  # fmt: skip
        if job_id is not None:
            await db.execute(update(Job).where(Job.id == job_id)
                             .values(status=JobStatus.FAILED, error_code=code))  # fmt: skip
        await db.commit()


# --------------------------------------------------------------------------------- read


def _params_out(params: dict[str, Any]) -> RunParams:
    return RunParams(
        preset=params["preset"],
        weights=WeightsOut(**{k: _r(v) for k, v in params["weights"].items()}),
        min_newcomers=params["min_newcomers"],
        min_performance=params["min_performance"],
        min_competency=params["min_competency"],
        mode=params["mode"],
    )


async def _confirmed_run(db: AsyncSession, project_id: uuid.UUID) -> uuid.UUID | None:
    return await db.scalar(select(Team.run_id).where(Team.project_id == project_id))


def _summary(run: FormationRun, confirmed: uuid.UUID | None) -> dict[str, Any]:
    result = run.result or {}
    verification = result.get("verification") or {}
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "preset": run.params.get("preset", "balanced"),
        "min_newcomers": int(run.params.get("min_newcomers", 0)),
        "fitness": result.get("fitness"),
        "optimal": verification.get("optimal"),
        "price_paisa": result.get("price_paisa") if result.get("feasible") else None,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "confirmed": confirmed == run.id,
    }


async def _visible_run(ctx: Ctx, run_id: uuid.UUID) -> FormationRun:
    run = await ctx.db.scalar(select(FormationRun).where(FormationRun.id == run_id))
    if run is None:
        raise NotFoundError
    project = await projrepo.get_project(ctx.db, run.project_id)
    if project is None or (project.client_id != ctx.uid and not ctx.principal.is_admin):
        raise NotFoundError
    return run


async def get_run(ctx: Ctx, run_id: uuid.UUID) -> FormationRunOut:
    authorize(ctx.principal, "formation.read")
    run = await _visible_run(ctx, run_id)
    project = await projrepo.get_project(ctx.db, run.project_id)
    confirmed = await _confirmed_run(ctx.db, run.project_id)
    result = RunResult.model_validate(run.result) if run.result else None
    can_confirm = (
        project is not None
        and project.client_id == ctx.uid
        and project.status == ProjectStatus.FORMING
        and run.status in FINISHED
        and result is not None
        and result.feasible
    )
    return FormationRunOut(
        id=run.id,
        project_id=run.project_id,
        status=run.status,
        job_id=run.job_id,
        seed=run.seed,
        settings_version=run.settings_version,
        params=_params_out(run.params),
        result=result,
        error_code=run.error_code,
        runtime_ms=run.runtime_ms,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        confirmed=confirmed == run.id,
        can_confirm=can_confirm,
    )


async def list_runs(ctx: Ctx, project_id: uuid.UUID) -> list[FormationRunSummary]:
    """The project's runs, newest first (D109)."""
    authorize(ctx.principal, "formation.read")
    project = await projrepo.get_project(ctx.db, project_id)
    if project is None or (project.client_id != ctx.uid and not ctx.principal.is_admin):
        raise NotFoundError
    rows = (await ctx.db.scalars(
        select(FormationRun).where(FormationRun.project_id == project_id)
        .order_by(FormationRun.created_at.desc(), FormationRun.id.desc()).limit(LIST_LIMIT)
    )).all()  # fmt: skip
    confirmed = await _confirmed_run(ctx.db, project_id)
    return [FormationRunSummary(**_summary(r, confirmed)) for r in rows]


async def admin_runs(
    ctx: Ctx, *, cursor: str | None, limit: int
) -> tuple[list[AdminRunOut], str | None]:
    """Every run, newest first, cursor-paged (admin console API, D110)."""
    authorize(ctx.principal, "admin.access")
    stmt = select(FormationRun, Project.title).join(Project, Project.id == FormationRun.project_id)
    if cursor is not None:
        at, rid = _decode_cursor(cursor)
        stmt = stmt.where(
            (FormationRun.created_at < at)
            | ((FormationRun.created_at == at) & (FormationRun.id < rid))
        )
    rows = (await ctx.db.execute(
        stmt.order_by(FormationRun.created_at.desc(), FormationRun.id.desc()).limit(limit + 1)
    )).tuples().all()  # fmt: skip
    teams = dict((await ctx.db.execute(select(Team.project_id, Team.run_id))).tuples().all())
    out = []
    for run, title in rows[:limit]:
        verified = (run.result or {}).get("admin_verification", {}).get("reproduced")
        out.append(AdminRunOut(**_summary(run, teams.get(run.project_id)), project_title=title,
                               runtime_ms=run.runtime_ms, verified=verified))  # fmt: skip
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1][0]
        next_cursor = _encode_cursor(last.created_at, last.id)
    return out, next_cursor


def _encode_cursor(at: datetime, rid: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{at.isoformat()}|{rid}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        at, rid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        parsed = datetime.fromisoformat(at)
        if parsed.tzinfo is None:
            raise ValueError("naive")
        return parsed, uuid.UUID(rid)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        raise DomainError(
            "That page link is no longer valid.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"cursor": "invalid"},
        ) from None


# ------------------------------------------------------------------------------- confirm


async def _create_team(
    db: AsyncSession,
    project: Project,
    run_id: uuid.UUID,
    team_bids: set[uuid.UUID],
    *,
    standing: Sequence[Bid],
    now: datetime,
) -> tuple[Team, list[Bid]]:
    """The team, its members, their unsent invitations (D108) and tentative reservations; the
    team's bids SELECTED and every other ACTIVE bid NOT_SELECTED. Returns (team, not selected)."""
    team = Team(project_id=project.id, run_id=run_id, confirmed_at=now)
    db.add(team)
    await db.flush()
    start = project.start_date or now.date()
    until = start + timedelta(days=project.deadline_days)
    not_selected: list[Bid] = []
    for bid in standing:
        if bid.id in team_bids:
            bid.status = BidStatus.SELECTED
            member = TeamMember(team_id=team.id, developer_id=bid.developer_id, bid_id=bid.id,
                                slot_id=bid.slot_id, price_paisa=bid.price_paisa,
                                days_needed=bid.days_needed)  # fmt: skip
            db.add(member)
            await db.flush()
            db.add(Invitation(team_member_id=member.id))
            db.add(AvailabilityReservation(
                developer_id=bid.developer_id, project_id=project.id,
                hours_per_week=bid.hours_per_week_committed, from_date=start, to_date=until,
                status=ReservationStatus.TENTATIVE,
            ))  # fmt: skip
        elif bid.status == BidStatus.ACTIVE:
            bid.status = BidStatus.NOT_SELECTED
            not_selected.append(bid)
        else:
            continue
        bid.version += 1
        bid.evaluated_at = now
    return team, not_selected


async def confirm(ctx: Ctx, run_id: uuid.UUID) -> ConfirmOut:
    """Confirm a finished run's recommended team (FORMING → TEAM_PENDING)."""
    authorize(ctx.principal, "formation.confirm")
    run = await _visible_run(ctx, run_id)
    project = await _own_project(ctx, run.project_id)
    if project.status != ProjectStatus.FORMING:
        raise InvalidStateTransition(project.status.value, [])
    result = RunResult.model_validate(run.result) if run.result else None
    if run.status not in FINISHED or result is None or not result.feasible:
        raise DomainError("Only a finished run with a team can be confirmed.",
                          code=ErrorCode.INVALID_STATE)  # fmt: skip
    team_bids = [m.bid_id for m in result.team]
    async with open_session(DbContext.system(), job=True) as db:
        locked = await db.scalar(select(Project).where(Project.id == project.id).with_for_update())
        if locked is None or locked.status != ProjectStatus.FORMING:
            raise InvalidStateTransition(
                locked.status.value if locked else "UNKNOWN", [], "This team was already confirmed."
            )
        standing = (await db.scalars(
            select(Bid).where(Bid.project_id == project.id,
                              Bid.status.in_([BidStatus.ACTIVE, BidStatus.INELIGIBLE]))
            .with_for_update()
        )).all()  # fmt: skip
        by_id = {b.id: b for b in standing}
        missing = [b for b in team_bids if b not in by_id or by_id[b].status != BidStatus.ACTIVE]
        if missing:
            raise DomainError(
                "A developer in this team withdrew their bid. Run team formation again.",
                code=ErrorCode.INVALID_STATE,
            )
        team, not_selected = await _create_team(db, project, run.id, set(team_bids),
                                                standing=standing, now=ctx.now)  # fmt: skip
        locked.status = ProjectStatus.TEAM_PENDING
        locked.version += 1
        for bid in not_selected:
            notify(db, bid.developer_id, "BID_NOT_SELECTED", title="Your bid was not selected",
                   body=f"The client formed a team for “{project.title}” without your bid. "
                   "See why, and what would have helped.", link=f"/dev/bids/{bid.id}")  # fmt: skip
        after = {"run_id": str(run.id), "project_id": str(project.id),
                 "members": len(team_bids), "not_selected": len(not_selected)}  # fmt: skip
        await write_audit(db, action="formation.confirmed", entity_type="team", entity_id=team.id,
                          actor_id=ctx.uid, actor_role=ctx.principal.role, after=after)  # fmt: skip
        await db.commit()
        team_id = team.id
    try:
        task_queue.enqueue(EXPLAIN_JOB_TYPE, str(run.id))
    except Exception:  # explanations can be rebuilt; the confirmation stands
        log.exception("formation_explanations_enqueue_failed", run_id=str(run.id))
    return ConfirmOut(team_id=team_id, project_status=ProjectStatus.TEAM_PENDING.value,
                      members=len(team_bids), invitations_sent=False)  # fmt: skip


# -------------------------------------------------------------------------------- verify


async def verify(ctx: Ctx, run_id: uuid.UUID) -> FormationRunAccepted:
    """Admin: re-run a finished run from its frozen inputs to check it reproduces (D109)."""
    authorize(ctx.principal, "admin.access")
    if not ctx.principal.has_step_up(ctx.now):
        raise DomainError(code=ErrorCode.STEP_UP_REQUIRED)
    run = await _visible_run(ctx, run_id)
    if run.status not in (*FINISHED, RunStatus.INFEASIBLE):
        raise DomainError("Only a finished run can be verified.", code=ErrorCode.INVALID_STATE)
    async with open_session(DbContext.system(), job=True) as db:
        job = Job(type=VERIFY_JOB_TYPE, status=JobStatus.QUEUED, progress=0, requested_by=ctx.uid,
                  result_ref=f"formation_run:{run.id}")  # fmt: skip
        db.add(job)
        await db.flush()
        await write_audit(
            db,
            action="formation.verify_requested",
            entity_type="formation_run",
            entity_id=run.id,
            actor_id=ctx.uid,
            actor_role=ctx.principal.role,
        )
        await db.commit()
        job_id = job.id
    try:
        task_queue.enqueue(VERIFY_JOB_TYPE, str(run.id), str(job_id))
    except Exception:
        log.exception("formation_verify_enqueue_failed", run_id=str(run.id))
        raise DomainError(code=ErrorCode.DEPENDENCY_UNAVAILABLE) from None
    return FormationRunAccepted(run_id=run.id, job_id=job_id, status=run.status, progress=0)


# --------------------------------------------------------------------------- explanation


async def bid_explanation(ctx: Ctx, bid_id: uuid.UUID) -> BidExplanationOut:
    """Why the caller's own bid was not selected (§9.8); 404 until there is one."""
    authorize(ctx.principal, "bid.explanation")
    bid = await ctx.db.scalar(select(Bid).where(Bid.id == bid_id))
    if bid is None or (bid.developer_id != ctx.uid and not ctx.principal.is_admin):
        raise NotFoundError
    if bid.status != BidStatus.NOT_SELECTED:
        raise NotFoundError
    # Explanations are written only for the confirmed run (one team per project), and RLS lets
    # the bidder read only their own. No join to `teams`: a bidder who isn't in the team can't
    # see it (RLS), which would hide their own explanation.
    row = await ctx.db.scalar(
        select(BidExplanation)
        .where(BidExplanation.bid_id == bid.id)
        .order_by(BidExplanation.created_at.desc())
        .limit(1)
    )
    if row is None:
        raise NotFoundError("The explanation is still being prepared. Check back in a minute.")
    title = await ctx.db.scalar(select(Project.title).where(Project.id == bid.project_id))
    gap = row.reasons.get("gap")
    compare = row.reasons.get("compare")
    return BidExplanationOut(
        bid_id=bid.id,
        project_title=title or "",
        reasons=list(row.reasons.get("codes", [])),
        main_gap=row.main_gap,
        hint=HINTS.get(row.main_gap or ""),
        gap=gap if isinstance(gap, (int, float)) and math.isfinite(gap) else None,
        price_counterfactual_paisa=row.price_counterfactual_paisa,
        compare=SlotComparison.model_validate(compare) if isinstance(compare, dict) else None,
        created_at=row.created_at,
    )
