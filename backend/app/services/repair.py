"""Team repair (spec §9.9; DECISIONS D126–D129, D137, D138).

`open_repair` is called inside the transaction that loses a member (decline, expiry, leave,
removal, a reopened slot closing, a budget raise). It supersedes any open proposal for that
departure, freezes a candidate snapshot from **current** data — reputation, Algorithm 1 eligibility
under the confirmed run's standards, availability, the 10-pending-invitations cap — read in that
SYSTEM session (D50, D128), and creates a COMPUTING proposal plus its job, requested by the
project's client (so the client's Team screen can follow it, D107). After the commit, `queue`
sends the job to the worker; `formation_runner.execute_repair` ranks the candidates.

The client then chooses a candidate (a replacement member, an invitation and a TENTATIVE
reservation; the bid moves NOT_SELECTED → SELECTED, D128), reopens the slot for 48 h (D126) or
raises the budget (D127).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.filtering import ReasonCode
from app.core import task_queue
from app.core.audit import write_audit
from app.core.authz import authorize
from app.core.clock import to_display
from app.core.errors import DomainError, ErrorCode, InvalidStateTransition, NotFoundError
from app.core.logging import get_logger
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.bidding import AvailabilityReservation, Bid, BidStatus, ReservationStatus
from app.models.formation import (
    BidExplanation,
    FormationRun,
    Invitation,
    MemberStatus,
    RepairProposal,
    RepairStatus,
    Team,
    TeamMember,
)
from app.models.foundation import Job, JobStatus
from app.models.identity import User
from app.models.projects import (
    MilestoneStatus,
    PlanBaseline,
    Project,
    ProjectSlot,
    ProjectStatus,
)
from app.repositories import projects as projrepo
from app.schemas.platform_settings import PlatformSettingsValues
from app.schemas.repair import ChooseIn, RaiseBudgetIn, RepairOut
from app.services import bids as bids_svc
from app.services import platform_settings, reputation_read
from app.services.context import Ctx
from app.services.notifications import notify

log = get_logger(__name__)

JOB_TYPE = "formation.repair"
SEED_BITS = 31
REOPEN_HOURS = 48
MAX_REOPENS = 2
MAX_PENDING_INVITATIONS = 10
BUDGET_CAP_PAISA = 10_000_000_000
OPEN = (RepairStatus.COMPUTING, RepairStatus.READY, RepairStatus.NO_CANDIDATES)
LIVE = (ProjectStatus.TEAM_PENDING, ProjectStatus.IN_PROGRESS)
DONE = (MilestoneStatus.APPROVED, MilestoneStatus.AUTO_APPROVED, MilestoneStatus.PAID)
REMAINING = (MemberStatus.INVITED, MemberStatus.ACTIVE)


def _system() -> Any:
    return open_session(DbContext.system(), job=True)


def queue(proposal: RepairProposal | None) -> None:
    """Send a committed proposal's job to the worker (no-op for None)."""
    if proposal is None:
        return
    try:
        task_queue.enqueue(JOB_TYPE, str(proposal.id))
    except Exception:  # the proposal stays COMPUTING; the client can ask again (budget/reopen)
        log.exception("repair_enqueue_failed", proposal_id=str(proposal.id))


async def _pending_counts(
    db: AsyncSession, developer_ids: list[uuid.UUID], now: datetime
) -> dict[uuid.UUID, int]:
    if not developer_ids:
        return {}
    rows = await db.execute(
        select(TeamMember.developer_id, func.count())
        .join(Invitation, Invitation.team_member_id == TeamMember.id)
        .where(
            TeamMember.developer_id.in_(developer_ids),
            Invitation.sent_at.is_not(None),
            Invitation.responded_at.is_(None),
            Invitation.expires_at > now,
        )
        .group_by(TeamMember.developer_id)
    )
    return {d: int(n) for d, n in rows.tuples().all()}


async def build_repair_snapshot(
    db: AsyncSession,
    project: Project,
    team: Team,
    departed: TeamMember,
    *,
    now: datetime,
    settings: PlatformSettingsValues,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(snapshot, params) for a repair: remaining members (locked) and the eligible candidates
    for the departed member's slot, in the formation snapshot's shape so `problem_from` reads it."""
    run = await db.get(FormationRun, team.run_id)
    if run is None:  # pragma: no cover - teams.run_id is a required FK
        raise NotFoundError
    params = dict(run.params)
    applied = (
        (run.result or {}).get("fairness", {}).get("applied_k", params.get("min_newcomers", 0))
    )
    params["min_newcomers"] = int(applied)
    slots = list(await projrepo.load_slots(db, project.id))
    slot = next(s for s in slots if s.id == departed.slot_id)
    members = list(
        (await db.scalars(select(TeamMember).where(TeamMember.team_id == team.id))).all()
    )
    remaining = [m for m in members if m.status in REMAINING and m.id != departed.id]
    current_devs = {m.developer_id for m in members if m.status in REMAINING}
    # Candidates: bids for this slot that are still in play — never selected, or placed on the
    # reopened slot — from developers who aren't in the team and didn't decline it.
    pool_bids = list(
        (
            await db.scalars(
                select(Bid).where(
                    Bid.project_id == project.id,
                    Bid.slot_id == slot.id,
                    Bid.status.in_([BidStatus.NOT_SELECTED, BidStatus.ACTIVE]),
                    Bid.developer_id.not_in(current_devs | {departed.developer_id}),
                )
            )
        ).all()
    )
    terms = bids_svc.project_terms(project, slots, settings)
    terms = bids_svc.Terms(
        p0=float(params.get("min_performance", terms.p0)),
        c0=float(params.get("min_competency", terms.c0)),
        budget_paisa=project.budget_paisa,
        slot_counts=terms.slot_counts,
    )
    today = to_display(now).date()
    ev = await bids_svc.evaluate(db, project, settings, today, terms, bids=pool_bids)
    rejected = dict(ev.result.rejected)
    unavailable = sum(1 for r in rejected.values() if r == ReasonCode.UNAVAILABLE)
    eligible = [b for b in pool_bids if str(b.id) in set(ev.result.eligible)]
    pending = await _pending_counts(db, [b.developer_id for b in eligible], now)
    excluded = [
        str(b.id) for b in eligible if pending.get(b.developer_id, 0) >= MAX_PENDING_INVITATIONS
    ]
    eligible = [b for b in eligible if str(b.id) not in set(excluded)]
    rem_bids = (
        {
            b.id: b
            for b in (
                await db.scalars(select(Bid).where(Bid.id.in_([m.bid_id for m in remaining])))
            ).all()
        }
        if remaining
        else {}
    )
    devs = [m.developer_id for m in remaining] + [b.developer_id for b in eligible]
    reps = await reputation_read.read_many(db, devs, settings)
    names = dict(
        (
            await db.execute(
                select(User.id, User.display_name).where(User.id.in_(devs or [uuid.uuid4()]))
            )
        )
        .tuples()
        .all()
    )
    labels = {s.id: s.label or "Role" for s in slots}
    inputs = {i.bid_id: i for i in ev.inputs}

    def row(
        bid: Bid, slot_id: uuid.UUID, *, competency: float, performance: float
    ) -> dict[str, Any]:
        rep = reps[bid.developer_id]
        return {
            "bid_id": str(bid.id),
            "developer_id": str(bid.developer_id),
            "developer_name": names.get(bid.developer_id, "Developer"),
            "slot_id": str(slot_id),
            "slot_label": labels.get(slot_id, "Role"),
            "competency": competency,
            "teamwork": rep.xm,
            "performance": performance,
            "days": bid.days_needed,
            "price_paisa": bid.price_paisa,
            "hours_per_week": bid.hours_per_week_committed,
            "newcomer": rep.is_newcomer,
            "skills": [str(next(s.skill_id for s in slots if s.id == slot_id))],
        }

    candidates: list[dict[str, Any]] = []
    for m in remaining:
        bid = rem_bids[m.bid_id]
        rep = reps[m.developer_id]
        candidates.append(row(bid, m.slot_id, competency=rep.c, performance=rep.p))
    for b in eligible:
        inp = inputs[str(b.id)]
        candidates.append(row(b, slot.id, competency=inp.c, performance=inp.p))
    milestones = list(await projrepo.load_milestones(db, project.id))
    skills = await projrepo.load_milestone_skills(db, [m.id for m in milestones])
    deps = await projrepo.load_dependencies(db, project.id)
    preds: dict[uuid.UUID, list[str]] = {m.id: [] for m in milestones}
    for d in deps:
        preds.setdefault(d.successor_id, []).append(str(d.predecessor_id))
    baseline = await db.scalar(
        select(PlanBaseline)
        .where(PlanBaseline.project_id == project.id)
        .order_by(PlanBaseline.version.desc())
        .limit(1)
    )
    baseline_days = int((baseline.cpm or {}).get("duration", 0)) if baseline is not None else 0
    plan: list[dict[str, Any]] = [
        {
            "id": str(m.id),
            "name": m.name,
            "duration_days": m.duration_days,
            "predecessors": preds.get(m.id, []),
            "skills": [str(s) for s in skills.get(m.id, [])],
            "done": m.status in DONE,
        }
        for m in milestones
    ]
    if baseline_days == 0 and plan:
        from app.algorithms.cpm import MilestoneInput, compute_cpm  # noqa: PLC0415

        baseline_days = compute_cpm(
            [MilestoneInput(p["id"], p["duration_days"], tuple(p["predecessors"])) for p in plan]
        ).duration
    departed_bid = await db.get(Bid, departed.bid_id)
    snapshot = {
        "candidates": candidates,
        "slots": {str(s.id): s.count for s in slots},
        "required_skills": sorted({str(s.skill_id) for s in slots}),
        "critical_skills": [],
        "deadline_days": project.deadline_days,
        "budget_after_fee_paisa": ev.proj.budget_after_fee_paisa,
        "remaining": list(range(len(remaining))),
        "pool": list(range(len(remaining), len(candidates))),
        "unavailable": unavailable,
        "excluded_pending_invitations": excluded,
        "departed": {
            "member_id": str(departed.id),
            "slot_id": str(slot.id),
            "skill_id": str(slot.skill_id),
            "slot_label": labels.get(slot.id, "Role"),
            "days": departed_bid.days_needed if departed_bid else departed.days_needed,
        },
        "plan": plan,
        "baseline_days": baseline_days,
        "started": project.status == ProjectStatus.IN_PROGRESS,
    }
    return snapshot, params


async def open_repair(
    db: AsyncSession,
    project: Project,
    team: Team,
    departed: TeamMember,
    *,
    now: datetime,
    settings: PlatformSettingsValues,
) -> RepairProposal:
    """Supersede the departure's open proposal and create a COMPUTING one with its job."""
    await db.execute(
        update(RepairProposal)
        .where(RepairProposal.departed_member_id == departed.id, RepairProposal.status.in_(OPEN))
        .values(status=RepairStatus.SUPERSEDED)
    )
    await db.flush()
    snapshot, params = await build_repair_snapshot(
        db, project, team, departed, now=now, settings=settings
    )
    version, _values = await platform_settings.get_active(db)
    job = Job(type=JOB_TYPE, status=JobStatus.QUEUED, progress=0, requested_by=project.client_id)
    db.add(job)
    await db.flush()
    proposal = RepairProposal(
        team_id=team.id,
        departed_member_id=departed.id,
        settings_version=version,
        seed=secrets.randbits(SEED_BITS),
        params=params,
        candidate_snapshot=snapshot,
        job_id=job.id,
    )
    db.add(proposal)
    await db.flush()
    job.result_ref = f"repair_proposal:{proposal.id}"
    await write_audit(
        db,
        action="team.repair_opened",
        entity_type="repair_proposal",
        entity_id=proposal.id,
        actor_role="SYSTEM",
        after={"departed_member_id": str(departed.id), "candidates": len(snapshot["pool"])},
    )
    return proposal


# --------------------------------------------------------------------------- client API


async def _client_project(
    db: AsyncSession, ctx: Ctx, project_id: uuid.UUID
) -> tuple[Project, Team]:
    project = await db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if project is None or (project.client_id != ctx.uid and not ctx.principal.is_admin):
        raise NotFoundError
    team = await db.scalar(select(Team).where(Team.project_id == project_id).with_for_update())
    if team is None:
        raise NotFoundError
    return project, team


def _out(p: RepairProposal) -> RepairOut:
    snap = p.candidate_snapshot or {}
    return RepairOut.model_validate(
        {
            "id": p.id,
            "status": p.status.value,
            "job_id": p.job_id,
            "created_at": p.created_at,
            "departed_member_id": p.departed_member_id,
            "slot_id": (snap.get("departed") or {}).get("slot_id"),
            "slot_label": (snap.get("departed") or {}).get("slot_label", "Role"),
            "candidates": p.candidates or [],
            "reasons": p.reasons or [],
            "impact": p.impact,
            "chosen_bid_id": p.chosen_bid_id,
        }
    )


async def get_repair(ctx: Ctx, project_id: uuid.UUID) -> RepairOut:
    """The latest proposal (COMPUTING included), client or admin only (sealed bids)."""
    authorize(ctx.principal, "team.repair")
    async with _system() as db:
        project = await db.get(Project, project_id)
        team = await db.scalar(select(Team).where(Team.project_id == project_id))
        if (
            project is None
            or team is None
            or (project.client_id != ctx.uid and not ctx.principal.is_admin)
        ):
            raise NotFoundError
        p = await db.scalar(
            select(RepairProposal)
            .where(RepairProposal.team_id == team.id)
            .order_by(RepairProposal.created_at.desc())
            .limit(1)
        )
        if p is None:
            raise NotFoundError
        return _out(p)


async def choose(ctx: Ctx, proposal_id: uuid.UUID, body: ChooseIn) -> RepairOut:
    """Invite a ranked candidate as the replacement (D128)."""
    authorize(ctx.principal, "team.repair.choose")
    settings = await active_settings(ctx.db)
    async with _system() as db:
        found = await db.get(RepairProposal, proposal_id)
        team = await db.get(Team, found.team_id) if found is not None else None
        if found is None or team is None:
            raise NotFoundError
        project, team = await _client_project(db, ctx, team.project_id)
        if project.client_id != ctx.uid:
            raise NotFoundError
        p = await db.scalar(
            select(RepairProposal).where(RepairProposal.id == proposal_id).with_for_update()
        )
        assert p is not None  # noqa: S101 - found above
        if p.status != RepairStatus.READY or project.status not in LIVE:
            raise InvalidStateTransition(p.status.value, [], "This proposal can't be used now.")
        offered = {c["bid_id"]: c for c in (p.candidates or [])}
        if str(body.bid_id) not in offered:
            raise DomainError(
                "Choose one of the proposed candidates.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={"bid_id": "not in this proposal"},
            )
        bid = await db.scalar(select(Bid).where(Bid.id == body.bid_id).with_for_update())
        if bid is None or bid.status not in (BidStatus.NOT_SELECTED, BidStatus.ACTIVE):
            raise DomainError(
                "This developer is no longer available. Recalculate the repair.",
                code=ErrorCode.INVALID_STATE,
            )
        pending = (await _pending_counts(db, [bid.developer_id], ctx.now)).get(bid.developer_id, 0)
        if pending >= MAX_PENDING_INVITATIONS:
            raise DomainError(
                "This developer has 10 invitations waiting for an answer. Recalculate the repair.",
                code=ErrorCode.LIMIT_REACHED,
            )
        member = TeamMember(
            team_id=team.id,
            developer_id=bid.developer_id,
            bid_id=bid.id,
            slot_id=bid.slot_id,
            price_paisa=bid.price_paisa,
            days_needed=bid.days_needed,
        )
        db.add(member)
        await db.flush()
        db.add(Invitation(team_member_id=member.id, is_replacement=True))
        today = to_display(ctx.now).date()
        start = project.start_date or today
        until = start + timedelta(days=project.deadline_days)
        if project.status == ProjectStatus.IN_PROGRESS:
            start = max(start, today)
        db.add(
            AvailabilityReservation(
                developer_id=bid.developer_id,
                project_id=project.id,
                hours_per_week=bid.hours_per_week_committed,
                from_date=start,
                to_date=max(until, start),
                status=ReservationStatus.TENTATIVE,
            )
        )
        bid.status = BidStatus.SELECTED  # NOT_SELECTED → SELECTED (D128)
        bid.version += 1
        p.status = RepairStatus.CHOSEN
        p.chosen_bid_id = bid.id
        await db.execute(
            update(BidExplanation)
            .where(BidExplanation.bid_id == bid.id)
            .values(
                reasons=BidExplanation.reasons.op("||")(func.jsonb_build_object("superseded", True))
            )
        )
        await db.flush()
        from app.services.team import send_invitations  # noqa: PLC0415 - team imports this module

        await send_invitations(db, project, team, ctx.now, settings, member_ids=[member.id])
        await write_audit(
            db,
            action="team.replacement_chosen",
            entity_type="repair_proposal",
            entity_id=p.id,
            actor_id=ctx.uid,
            actor_role="CLIENT",
            after={"bid_id": str(bid.id)},
        )
        out = _out(p)
        await db.commit()
    return out


async def _open_proposal(
    db: AsyncSession,
    team: Team,
    *,
    slot_id: uuid.UUID | None = None,
    status: RepairStatus | None = None,
) -> RepairProposal | None:
    rows = (
        await db.scalars(
            select(RepairProposal)
            .where(RepairProposal.team_id == team.id, RepairProposal.status.in_(OPEN))
            .order_by(RepairProposal.created_at.desc())
        )
    ).all()
    for p in rows:
        if slot_id is not None and (p.candidate_snapshot.get("departed") or {}).get(
            "slot_id"
        ) != str(slot_id):
            continue
        if status is not None and p.status != status:
            continue
        return p
    return None


async def reopen_slot(ctx: Ctx, project_id: uuid.UUID, slot_id: uuid.UUID) -> RepairOut:
    """D126: from a NO_CANDIDATES proposal, open the slot to new bids for 48 h (≤ 2 times)."""
    authorize(ctx.principal, "team.repair.choose")
    async with _system() as db:
        project, team = await _client_project(db, ctx, project_id)
        if project.client_id != ctx.uid:
            raise NotFoundError
        if project.status not in LIVE:
            raise InvalidStateTransition(project.status.value, [])
        slot = next((s for s in await projrepo.load_slots(db, project_id) if s.id == slot_id), None)
        if slot is None:
            raise NotFoundError
        p = await _open_proposal(db, team, slot_id=slot_id, status=RepairStatus.NO_CANDIDATES)
        if p is None:
            raise DomainError(
                "Reopen a slot only when team repair found nobody for it.",
                code=ErrorCode.INVALID_STATE,
            )
        if slot.reopen_count >= MAX_REOPENS:
            raise DomainError("This slot was already reopened twice.", code=ErrorCode.LIMIT_REACHED)
        if slot.reopened_until is not None and slot.reopened_until > ctx.now:
            raise DomainError("This slot is already open for bids.", code=ErrorCode.INVALID_STATE)
        slot.reopened_until = ctx.now + timedelta(hours=REOPEN_HOURS)
        slot.reopen_count += 1
        await write_audit(
            db,
            action="project.slot_reopened",
            entity_type="project_slot",
            entity_id=slot.id,
            actor_id=ctx.uid,
            actor_role="CLIENT",
            after={"until": slot.reopened_until.isoformat(), "count": slot.reopen_count},
        )
        out = _out(p)
        await db.commit()
    return out


async def raise_budget(
    ctx: Ctx, project_id: uuid.UUID, body: RaiseBudgetIn, if_match: int | None
) -> RepairOut:
    """D127: from a REMAINING_BUDGET_TOO_LOW proposal, raise the budget by at least the shortfall;
    C is recomputed (A10) and the repair recomputed."""
    authorize(ctx.principal, "team.repair.choose")
    settings = await active_settings(ctx.db)
    async with _system() as db:
        project, team = await _client_project(db, ctx, project_id)
        if project.client_id != ctx.uid:
            raise NotFoundError
        if project.status not in LIVE:
            raise InvalidStateTransition(project.status.value, [])
        if if_match is not None and if_match != project.version:
            raise DomainError(
                "This project was changed in another tab. Reload and try again.",
                code=ErrorCode.VERSION_CONFLICT,
                extra={"current_version": project.version},
            )
        p = None
        shortfall = 0
        for cand in [await _open_proposal(db, team, status=RepairStatus.NO_CANDIDATES)]:
            for r in (cand.reasons if cand is not None else None) or []:
                if isinstance(r, dict) and r.get("code") == "REMAINING_BUDGET_TOO_LOW":
                    p, shortfall = cand, int(r.get("shortfall_paisa") or 0)
        if p is None:
            raise DomainError(
                "Raise the budget only when team repair says it is too low.",
                code=ErrorCode.INVALID_STATE,
            )
        fee = settings.pay.platform_fee_bp
        # The shortfall is against C (after the fee); the budget needed before the fee is larger.
        needed = project.budget_paisa + -(-shortfall * 10_000 // (10_000 - fee))
        if body.budget_paisa < needed:
            raise DomainError(
                "The new budget must cover the shortfall.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={"budget_paisa": f"at least {needed}"},
            )
        if body.budget_paisa > BUDGET_CAP_PAISA:
            raise DomainError(
                "That budget is above the limit.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={"budget_paisa": f"at most {BUDGET_CAP_PAISA}"},
            )
        old = project.budget_paisa
        project.budget_paisa = body.budget_paisa
        project.version += 1
        departed = await db.get(TeamMember, p.departed_member_id)
        assert departed is not None  # noqa: S101 - FK
        new = await open_repair(db, project, team, departed, now=ctx.now, settings=settings)
        await write_audit(
            db,
            action="project.budget_raised",
            entity_type="project",
            entity_id=project.id,
            actor_id=ctx.uid,
            actor_role="CLIENT",
            before={"budget_paisa": old},
            after={"budget_paisa": body.budget_paisa},
        )
        out = _out(new)
        await db.commit()
    queue(new)
    return out


async def close_reopened(now: datetime) -> int:
    """`lifecycle.expire`: close reopened slots whose 48 h ended; recompute their repair and tell
    the client (D126)."""
    closed = 0
    async with _system() as db:
        settings = await active_settings(db)
        slots = (
            await db.scalars(select(ProjectSlot).where(ProjectSlot.reopened_until <= now))
        ).all()
        slot_ids = [s.id for s in slots]
    for slot_id in slot_ids:
        proposal = None
        async with _system() as db:
            slot = await db.scalar(
                select(ProjectSlot).where(ProjectSlot.id == slot_id).with_for_update()
            )
            if slot is None or slot.reopened_until is None or slot.reopened_until > now:
                continue
            slot.reopened_until = None
            project = await db.scalar(
                select(Project).where(Project.id == slot.project_id).with_for_update()
            )
            team = await db.scalar(
                select(Team).where(Team.project_id == slot.project_id).with_for_update()
            )
            if project is not None and team is not None and project.status in LIVE:
                p = await _open_proposal(db, team, slot_id=slot.id)
                departed = await db.get(TeamMember, p.departed_member_id) if p else None
                if departed is not None:
                    proposal = await open_repair(
                        db, project, team, departed, now=now, settings=settings
                    )
                notify(
                    db,
                    project.client_id,
                    "SLOT_CLOSED",
                    title="Reopened place closed",
                    body=f"The reopened place on “{project.title}” closed. DevSync is ranking "
                    "the new bids.",
                    link=f"/client/projects/{project.id}/team",
                )
            await db.commit()
            closed += 1
        queue(proposal)
    return closed
