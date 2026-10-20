"""Sealed bids: create, edit, withdraw, the eligibility preview and the client's bids view.

Algorithm 1 (`algorithms/filtering.py`) decides eligibility; this service builds its inputs from
the bids, the project and the developers' reputation snapshots (via `reputation_read`), and never
lets one developer see another's bid (§14.5 — enforced again by RLS). Bids may be placed or edited
only while the project is `BIDDING` (§8); an invalid state is a 409 `INVALID_STATE`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms import availability as avail
from app.algorithms.filtering import (
    Advancement,
    BidInput,
    FilterParams,
    FilterResult,
    Mode,
    ProjectInput,
    ReasonCode,
    SlotSpec,
    classify_bid,
    filter_bids,
)
from app.core.audit import write_audit
from app.core.errors import DomainError, ErrorCode, NotFoundError
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.bidding import Bid, BidStatus
from app.models.identity import User
from app.models.profiles import DeveloperProfile, SkillEvidence
from app.models.projects import Project, ProjectSlot, ProjectStatus
from app.repositories import bids as repo
from app.repositories import projects as projrepo
from app.schemas.bids import (
    BidCreate,
    BidOut,
    BidUpdate,
    ClientBidOut,
    ClientBidsOut,
    ConstraintCheck,
    EligibilityIn,
    EligibilityOut,
    RelaxationOut,
    SlotCoverage,
)
from app.schemas.platform_settings import PlatformSettingsValues
from app.services import reputation_read
from app.services.context import Ctx

_ADVANCEMENT = Advancement.C  # Balanced default until the client picks a preset at formation.

_REASON_TEXT = {
    ReasonCode.LOW_PERFORMANCE: "Performance below the project minimum",
    ReasonCode.LOW_COMPETENCY: "Competency below the project minimum",
    ReasonCode.TOO_SLOW: "Needs more days than the deadline allows",
    ReasonCode.OVER_BUDGET: "Price above the project budget",
    ReasonCode.NO_SKILL_EVIDENCE: "No passing skill test for this slot's skill",
    ReasonCode.SKILL_MISMATCH: "You don't list this slot's skill",
    ReasonCode.UNAVAILABLE: "Not enough free hours over the project period",
    ReasonCode.SUSPENDED: "Account not active",
    ReasonCode.SELF_DEALING: "Conflict of interest with this client",
    ReasonCode.NOT_SHORTLISTED: "Eligible but not in the top shortlist for this slot",
}


# --------------------------------------------------------------------------- loading


async def _bidding_project(ctx: Ctx, project_id: uuid.UUID) -> Project:
    project = await projrepo.get_project(ctx.db, project_id)
    if project is None:
        raise NotFoundError
    if project.status != ProjectStatus.BIDDING:
        raise DomainError("This project is not open for bids.", code=ErrorCode.INVALID_STATE)
    return project


async def _own_project(ctx: Ctx, project_id: uuid.UUID) -> Project:
    project = await projrepo.get_project(ctx.db, project_id)
    if project is None or (project.client_id != ctx.uid and not ctx.principal.is_admin):
        raise NotFoundError
    return project


def _period(project: Project, today: date) -> avail.Period:
    start = project.start_date or today
    return avail.Period(from_=start, to=start + timedelta(days=project.deadline_days))


async def _evidence_scores(db: AsyncSession, developer_id: uuid.UUID) -> dict[uuid.UUID, float]:
    """Best skill-evidence score per skill for a developer (for the newcomer rule)."""
    rows = await db.execute(
        select(SkillEvidence.skill_id, SkillEvidence.score).where(
            SkillEvidence.user_id == developer_id
        )
    )
    best: dict[uuid.UUID, float] = {}
    for skill_id, score in rows:
        best[skill_id] = max(best.get(skill_id, 0.0), float(score))
    return best


async def _available(
    db: AsyncSession, developer_id: uuid.UUID, project: Project, commitment: int, today: date
) -> bool:
    reservations = [
        avail.Reservation(avail.Period(r.from_date, r.to_date), r.hours_per_week)
        for r in await repo.confirmed_reservations(db, developer_id)
        if r.project_id != project.id
    ]
    profile = await db.scalar(
        select(DeveloperProfile).where(DeveloperProfile.user_id == developer_id)
    )
    profile_hours = profile.hours_per_week if profile else 20
    return avail.is_feasible(reservations, _period(project, today), commitment, profile_hours)


def _project_input(project: Project, slots: Sequence[ProjectSlot], fee_bp: int) -> ProjectInput:
    after_fee = project.budget_paisa * (10_000 - fee_bp) // 10_000
    return ProjectInput(
        deadline_days=project.deadline_days,
        budget_after_fee_paisa=after_fee,
        slots={str(s.id): SlotSpec(skill_id=str(s.skill_id), count=s.count) for s in slots},
    )


def _params(settings: PlatformSettingsValues, team_size: int) -> FilterParams:
    f = settings.filter
    return FilterParams(
        p0=float(f.P0),
        c0=float(f.C0),
        advancement=_ADVANCEMENT,
        team_size=team_size,
        newcomer_pass_mark=float(settings.newcomer.pass_mark),
        newcomer_competency_check=f.newcomer_competency_check,
        relax_step=float(f.relax_step),
        relax_max_steps=f.relax_max_steps,
        shortlist_factor=f.shortlist_factor,
        shortlist_min=f.shortlist_min,
        mode=Mode(settings.algorithm.mode),
    )


# --------------------------------------------------------------------------- write


async def _default_hours(ctx: Ctx, override: int | None) -> int:
    if override is not None:
        return override
    profile = await ctx.db.scalar(
        select(DeveloperProfile).where(DeveloperProfile.user_id == ctx.uid)
    )
    return min(20, profile.hours_per_week if profile else 20)


def _bid_out(bid: Bid) -> BidOut:
    return BidOut(
        id=bid.id,
        project_id=bid.project_id,
        slot_id=bid.slot_id,
        status=bid.status.value,
        price_paisa=bid.price_paisa,
        days_needed=bid.days_needed,
        proposal=bid.proposal,
        expected_contribution=bid.expected_contribution,
        portfolio_item_ids=[uuid.UUID(str(x)) for x in bid.portfolio_item_ids],
        hours_per_week_committed=bid.hours_per_week_committed,
        created_at=bid.created_at,
        updated_at=bid.updated_at,
    )


async def create_bid(ctx: Ctx, project_id: uuid.UUID, body: BidCreate) -> BidOut:
    await _bidding_project(ctx, project_id)
    slots = {s.id: s for s in await projrepo.load_slots(ctx.db, project_id)}
    if body.slot_id not in slots:
        raise DomainError(
            "That slot is not part of this project.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"slot_id": "unknown slot"},
        )
    if await repo.active_bid(ctx.db, project_id, ctx.uid) is not None:
        raise DomainError(
            "You already have an active bid on this project.", code=ErrorCode.INVALID_STATE
        )
    bid = Bid(
        project_id=project_id,
        developer_id=ctx.uid,
        slot_id=body.slot_id,
        price_paisa=body.price_paisa,
        days_needed=body.days_needed,
        proposal=body.proposal.strip(),
        expected_contribution=body.expected_contribution.strip(),
        portfolio_item_ids=[str(x) for x in body.portfolio_item_ids],
        hours_per_week_committed=await _default_hours(ctx, body.hours_per_week_committed),
        status=BidStatus.ACTIVE,
    )
    ctx.db.add(bid)
    await ctx.db.flush()
    await write_audit(
        ctx.db, action="bid.create", entity_type="bid", entity_id=bid.id, actor_id=ctx.uid
    )
    await ctx.db.commit()
    await ctx.db.refresh(bid)
    return _bid_out(bid)


async def _own_bid(ctx: Ctx, bid_id: uuid.UUID) -> Bid:
    bid = await repo.get_bid(ctx.db, bid_id)
    if bid is None or bid.developer_id != ctx.uid:
        raise NotFoundError
    return bid


async def update_bid(ctx: Ctx, bid_id: uuid.UUID, body: BidUpdate) -> BidOut:
    bid = await _own_bid(ctx, bid_id)
    if bid.status != BidStatus.ACTIVE:
        raise DomainError("This bid can no longer be edited.", code=ErrorCode.INVALID_STATE)
    await _bidding_project(ctx, bid.project_id)
    data = body.model_dump(exclude_unset=True)
    if "slot_id" in data:
        slots = {s.id for s in await projrepo.load_slots(ctx.db, bid.project_id)}
        if data["slot_id"] not in slots:
            raise DomainError(
                "That slot is not part of this project.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={"slot_id": "unknown slot"},
            )
    for field in ("slot_id", "price_paisa", "days_needed", "hours_per_week_committed"):
        if field in data and data[field] is not None:
            setattr(bid, field, data[field])
    if data.get("proposal") is not None:
        bid.proposal = data["proposal"].strip()
    if data.get("expected_contribution") is not None:
        bid.expected_contribution = data["expected_contribution"].strip()
    if data.get("portfolio_item_ids") is not None:
        bid.portfolio_item_ids = [str(x) for x in data["portfolio_item_ids"]]
    await write_audit(
        ctx.db, action="bid.update", entity_type="bid", entity_id=bid.id, actor_id=ctx.uid
    )
    await ctx.db.commit()
    await ctx.db.refresh(bid)
    return _bid_out(bid)


async def withdraw_bid(ctx: Ctx, bid_id: uuid.UUID) -> None:
    bid = await _own_bid(ctx, bid_id)
    if bid.status != BidStatus.ACTIVE:
        raise DomainError("This bid is not active.", code=ErrorCode.INVALID_STATE)
    await _bidding_project(ctx, bid.project_id)
    bid.status = BidStatus.WITHDRAWN
    await write_audit(
        ctx.db, action="bid.withdraw", entity_type="bid", entity_id=bid.id, actor_id=ctx.uid
    )
    await ctx.db.commit()


async def my_bids(ctx: Ctx) -> list[BidOut]:
    return [_bid_out(b) for b in await repo.list_for_developer(ctx.db, ctx.uid)]


# --------------------------------------------------------------------------- eligibility preview


async def eligibility_preview(
    ctx: Ctx, project_id: uuid.UUID, body: EligibilityIn
) -> EligibilityOut:
    project = await _bidding_project(ctx, project_id)
    settings = await active_settings(ctx.db)
    slots = {s.id: s for s in await projrepo.load_slots(ctx.db, project_id)}
    slot = slots.get(body.slot_id)
    if slot is None:
        raise DomainError(
            "That slot is not part of this project.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"slot_id": "unknown slot"},
        )
    rep = await reputation_read.read_one(ctx.db, ctx.uid, settings)
    dev_skills = await repo.developer_skill_ids(ctx.db, ctx.uid)
    evidence = await _evidence_scores(ctx.db, ctx.uid)
    commitment = await _default_hours(ctx, body.hours_per_week_committed)
    bid = BidInput(
        bid_id="preview",
        slot_id=str(slot.id),
        skill_id=str(slot.skill_id),
        developer_id=str(ctx.uid),
        is_newcomer=rep.is_newcomer,
        p=rep.p,
        c=rep.c,
        t_days=body.days_needed,
        c_paisa=body.price_paisa,
        skill_evidence_score=evidence.get(slot.skill_id),
        has_slot_skill=slot.skill_id in dev_skills,
        active=ctx.principal.is_active,
        available=await _available(ctx.db, ctx.uid, project, commitment, ctx.now.date()),
        self_dealing=False,
    )
    proj = _project_input(project, list(slots.values()), settings.pay.platform_fee_bp)
    params = _params(settings, project.team_size)
    reason = classify_bid(bid, proj, params, params.p0, params.c0)
    checks = _preview_checks(bid, proj, params)
    message = (
        "You meet every requirement."
        if reason is None
        else (f"Would be filtered out: {_REASON_TEXT[reason].lower()}.")
    )
    return EligibilityOut(
        eligible=reason is None,
        reason=reason.value if reason else None,
        message=message,
        checks=checks,
    )


def _preview_checks(
    bid: BidInput, proj: ProjectInput, params: FilterParams
) -> list[ConstraintCheck]:
    newcomer = bid.is_newcomer and params.mode is Mode.DEVSYNC
    checks = [
        ConstraintCheck(
            name="days",
            ok=bid.t_days <= proj.deadline_days,
            detail=f"{bid.t_days} of {proj.deadline_days} days",
        ),
        ConstraintCheck(
            name="price",
            ok=bid.c_paisa <= proj.budget_after_fee_paisa,
            detail="within budget" if bid.c_paisa <= proj.budget_after_fee_paisa else "over budget",
        ),
        ConstraintCheck(name="skill", ok=bid.has_slot_skill, detail="skill listed"),
        ConstraintCheck(name="available", ok=bid.available, detail="hours available"),
    ]
    if newcomer:
        has = (
            bid.skill_evidence_score is not None
            and bid.skill_evidence_score >= params.newcomer_pass_mark
        )
        checks.append(ConstraintCheck(name="skill_evidence", ok=has, detail="passing skill test"))
    else:
        checks.append(
            ConstraintCheck(
                name="performance",
                ok=bid.p >= params.p0 - 1e-9,
                detail=f"P {bid.p:.2f} ≥ {params.p0:.2f}",
            )
        )
        checks.append(
            ConstraintCheck(
                name="competency",
                ok=bid.c >= params.c0 - 1e-9,
                detail=f"C {bid.c:.2f} ≥ {params.c0:.2f}",
            )
        )
    return checks


# --------------------------------------------------------------------------- client bids view


async def evaluate_project(
    db: AsyncSession, project: Project, settings: PlatformSettingsValues, today: date
) -> tuple[list[Bid], FilterResult, dict[uuid.UUID, reputation_read.ReputationView]]:
    """Run Algorithm 1 over a project's active bids. Ctx-free so the deadline job can reuse it."""
    bids = list(await repo.list_active_for_project(db, project.id))
    slots = list(await projrepo.load_slots(db, project.id))
    reps = await reputation_read.read_many(db, [b.developer_id for b in bids], settings)
    inputs: list[BidInput] = []
    for b in bids:
        rep = reps[b.developer_id]
        dev_skills = await repo.developer_skill_ids(db, b.developer_id)
        evidence = await _evidence_scores(db, b.developer_id)
        slot = next((s for s in slots if s.id == b.slot_id), None)
        inputs.append(
            BidInput(
                bid_id=str(b.id),
                slot_id=str(b.slot_id),
                skill_id=str(slot.skill_id) if slot else "",
                developer_id=str(b.developer_id),
                is_newcomer=rep.is_newcomer,
                p=rep.p,
                c=rep.c,
                t_days=b.days_needed,
                c_paisa=b.price_paisa,
                skill_evidence_score=(evidence.get(slot.skill_id) if slot is not None else None),
                has_slot_skill=slot is not None and slot.skill_id in dev_skills,
                active=True,
                available=await _available(
                    db, b.developer_id, project, b.hours_per_week_committed, today
                ),
                self_dealing=False,
            )
        )
    proj = _project_input(project, slots, settings.pay.platform_fee_bp)
    result = filter_bids(inputs, proj, _params(settings, project.team_size))
    return bids, result, reps


async def client_bids(ctx: Ctx, project_id: uuid.UUID) -> ClientBidsOut:
    project = await _own_project(ctx, project_id)
    settings = await active_settings(ctx.db)
    # Eligibility needs each bidder's skills/evidence, which the client can't read directly;
    # evaluate in a SYSTEM session (the caller is already confirmed as the project's owner, and
    # only the verdict — not raw developer data — is returned). See migration 0006.
    async with open_session(DbContext.system(), job=True) as sysdb:
        bids, result, reps = await evaluate_project(sysdb, project, settings, ctx.now.date())
        slots = {s.id: s for s in await projrepo.load_slots(sysdb, project_id)}
        names = {
            u.id: u.display_name
            for u in await sysdb.scalars(
                select(User).where(User.id.in_([b.developer_id for b in bids]))
            )
        }
        rejected = dict(result.rejected)
        rows: list[ClientBidOut] = []
        for b in bids:
            bid_id = str(b.id)
            reasons: list[str] = []
            if bid_id in rejected:
                reasons = [rejected[bid_id].value]
            elif bid_id in result.not_shortlisted:
                reasons = [ReasonCode.NOT_SHORTLISTED.value]
            rep = reps[b.developer_id]
            slot = slots.get(b.slot_id)
            rows.append(
                ClientBidOut(
                    id=b.id,
                    developer_id=b.developer_id,
                    developer_name=names.get(b.developer_id, "Developer"),
                    slot_id=b.slot_id,
                    slot_label=slot.label if slot else "",
                    status=b.status.value,
                    price_paisa=b.price_paisa,
                    days_needed=b.days_needed,
                    competency=rep.c,
                    performance=rep.p,
                    is_newcomer=rep.is_newcomer,
                    seeded=rep.seeded,
                    eligible=bid_id in result.eligible,
                    reasons=reasons,
                )
            )
        coverage = [
            SlotCoverage(
                slot_id=s.id,
                slot_label=s.label,
                needed=s.count,
                eligible=sum(
                    1 for b in bids if b.slot_id == s.id and str(b.id) in result.eligible
                ),
            )
            for s in slots.values()
        ]
    return ClientBidsOut(
        bids=rows,
        coverage=coverage,
        relaxations=[RelaxationOut(step=r.step, p0=r.p0, c0=r.c0) for r in result.relaxations],
        too_few=result.too_few,
    )
