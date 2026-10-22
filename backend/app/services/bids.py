"""Sealed bids: create, edit, withdraw, the eligibility preview and the client's bids view.

Algorithm 1 (`algorithms/filtering.py`) decides eligibility; this service builds its inputs from
the bids, the project and the developers' reputation snapshots (via `reputation_read`), and never
lets one developer see another's bid (§14.5 — enforced again by RLS). Bids may be placed, edited
or withdrawn only while the project is `BIDDING` **and** its bidding deadline has not passed (§8,
§13.5 #11 "edit/withdraw until deadline"); otherwise 409 `INVALID_STATE`. The deadline job moves
the project on later, so the time check does not depend on when the job runs (D54).

A project's minimum standards are its own `min_performance`/`min_competency` when the client
lowered them (too-few-bids actions, `services/bidding_terms.py`), else the platform `filter.P0`/
`filter.C0`. Bidders' skills, evidence, hours and reservations are read in batches, so the
client's view costs a fixed number of queries however many bids a project has.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms import availability as avail
from app.algorithms.filtering import (
    Advancement,
    BidInput,
    Check,
    FilterParams,
    FilterResult,
    Mode,
    ProjectInput,
    ReasonCode,
    SlotSpec,
    cheapest_team_cost,
    classify_bid,
    explain_bid,
    filter_bids,
)
from app.core.audit import write_audit
from app.core.errors import DomainError, ErrorCode, NotFoundError
from app.core.money import format_taka
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.bidding import Bid, BidStatus
from app.models.identity import User
from app.models.profiles import DeveloperProfile, Skill
from app.models.projects import Project, ProjectSlot, ProjectStatus
from app.repositories import bids as repo
from app.repositories import projects as projrepo
from app.schemas.bids import (
    BidCreate,
    BiddingWindow,
    BidOut,
    BidUpdate,
    ClientBidOut,
    ClientBidsOut,
    ConstraintCheck,
    EligibilityIn,
    EligibilityOut,
    NewcomerEvidence,
    PortfolioRef,
    RelaxationOut,
    SlotCoverage,
    TeamCostOut,
    Thresholds,
)
from app.schemas.platform_settings import PlatformSettingsValues
from app.services import marketplace, reputation_read
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


# --------------------------------------------------------------------------- terms


@dataclass(frozen=True)
class Terms:
    """The parts of a project Algorithm 1 depends on; a what-if evaluation overrides them."""

    p0: float
    c0: float
    budget_paisa: int
    slot_counts: dict[uuid.UUID, int]


def default_thresholds(settings: PlatformSettingsValues) -> tuple[float, float]:
    return float(settings.filter.P0), float(settings.filter.C0)


def threshold_floor(settings: PlatformSettingsValues) -> tuple[float, float]:
    """How far a client may lower the standards: the default minus the full automatic
    relaxation (3 × 0.05 by default → P 45 → 30, C 40 → 25; DECISIONS D54)."""
    f = settings.filter
    span = float(f.relax_step) * f.relax_max_steps
    return max(0.0, round(float(f.P0) - span, 2)), max(0.0, round(float(f.C0) - span, 2))


def project_terms(
    project: Project, slots: Sequence[ProjectSlot], settings: PlatformSettingsValues
) -> Terms:
    p0, c0 = default_thresholds(settings)
    return Terms(
        p0=float(project.min_performance) if project.min_performance is not None else p0,
        c0=float(project.min_competency) if project.min_competency is not None else c0,
        budget_paisa=project.budget_paisa,
        slot_counts={s.id: s.count for s in slots},
    )


def bidding_closed(project: Project, now: datetime) -> bool:
    return project.bidding_deadline is not None and now >= project.bidding_deadline


# A shortfall the client leaves alone (§9.19 says what to offer, not when to stop): a reminder a
# week after bidding closed, and the project closes on its own a week later (D54). Cancelling is
# free before a team is formed, and the date is shown on the Bids page from the start.
REMIND_AFTER = timedelta(days=7)
AUTO_CLOSE_AFTER = timedelta(days=14)


def auto_close_at(project: Project) -> datetime | None:
    return project.bidding_deadline + AUTO_CLOSE_AFTER if project.bidding_deadline else None


# --------------------------------------------------------------------------- loading


async def _bidding_project(ctx: Ctx, project_id: uuid.UUID) -> Project:
    project = await projrepo.get_project(ctx.db, project_id)
    if project is None:
        raise NotFoundError
    if project.status != ProjectStatus.BIDDING:
        raise DomainError("This project is not open for bids.", code=ErrorCode.INVALID_STATE)
    if bidding_closed(project, ctx.now):
        raise DomainError("Bidding for this project has closed.", code=ErrorCode.INVALID_STATE)
    return project


async def _own_project(ctx: Ctx, project_id: uuid.UUID) -> Project:
    project = await projrepo.get_project(ctx.db, project_id)
    if project is None or (project.client_id != ctx.uid and not ctx.principal.is_admin):
        raise NotFoundError
    return project


def _period(project: Project, today: date) -> avail.Period:
    start = project.start_date or today
    return avail.Period(from_=start, to=start + timedelta(days=project.deadline_days))


def _project_input(
    terms: Terms, project: Project, slots: Sequence[ProjectSlot], fee_bp: int
) -> ProjectInput:
    after_fee = terms.budget_paisa * (10_000 - fee_bp) // 10_000
    return ProjectInput(
        deadline_days=project.deadline_days,
        budget_after_fee_paisa=after_fee,
        slots={
            str(s.id): SlotSpec(
                skill_id=str(s.skill_id), count=terms.slot_counts.get(s.id, s.count)
            )
            for s in slots
        },
    )


def _params(settings: PlatformSettingsValues, terms: Terms) -> FilterParams:
    f = settings.filter
    return FilterParams(
        p0=terms.p0,
        c0=terms.c0,
        advancement=_ADVANCEMENT,
        team_size=sum(terms.slot_counts.values()),
        newcomer_pass_mark=float(settings.newcomer.pass_mark),
        newcomer_competency_check=f.newcomer_competency_check,
        relax_step=float(f.relax_step),
        relax_max_steps=f.relax_max_steps,
        shortlist_factor=f.shortlist_factor,
        shortlist_min=f.shortlist_min,
        mode=Mode(settings.algorithm.mode),
    )


@dataclass(frozen=True)
class _BidderData:
    skills: dict[uuid.UUID, set[uuid.UUID]]
    evidence: dict[uuid.UUID, dict[uuid.UUID, float]]
    hours: dict[uuid.UUID, int]
    reservations: dict[uuid.UUID, list[avail.Reservation]]


async def _bidder_data(
    db: AsyncSession, developer_ids: Sequence[uuid.UUID], project_id: uuid.UUID
) -> _BidderData:
    raw = await repo.confirmed_reservations_by_developer(db, developer_ids)
    return _BidderData(
        skills=await repo.skills_by_developer(db, developer_ids),
        evidence=await repo.best_evidence_by_developer(db, developer_ids),
        hours=await repo.profile_hours_by_developer(db, developer_ids),
        reservations={
            dev: [
                avail.Reservation(avail.Period(r.from_date, r.to_date), r.hours_per_week)
                for r in rows
                if r.project_id != project_id
            ]
            for dev, rows in raw.items()
        },
    )


def _bid_input(
    *,
    bid_id: str,
    developer_id: uuid.UUID,
    slot: ProjectSlot | None,
    rep: reputation_read.ReputationView,
    data: _BidderData,
    days: int,
    price: int,
    commitment: int,
    period: avail.Period,
    active: bool,
) -> BidInput:
    evidence = data.evidence.get(developer_id, {})
    return BidInput(
        bid_id=bid_id,
        slot_id=str(slot.id) if slot else "",
        skill_id=str(slot.skill_id) if slot else "",
        developer_id=str(developer_id),
        is_newcomer=rep.is_newcomer,
        p=rep.p,
        c=rep.c,
        t_days=days,
        c_paisa=price,
        skill_evidence_score=evidence.get(slot.skill_id) if slot is not None else None,
        has_slot_skill=slot is not None and slot.skill_id in data.skills.get(developer_id, set()),
        active=active,
        available=avail.is_feasible(
            data.reservations.get(developer_id, []),
            period,
            commitment,
            data.hours.get(developer_id, 20),
        ),
        self_dealing=False,
    )


# --------------------------------------------------------------------------- write


async def _default_hours(ctx: Ctx, override: int | None) -> int:
    if override is not None:
        return override
    profile = await ctx.db.scalar(
        select(DeveloperProfile).where(DeveloperProfile.user_id == ctx.uid)
    )
    return min(20, profile.hours_per_week if profile else 20)


async def _check_portfolio(ctx: Ctx, item_ids: Sequence[uuid.UUID]) -> list[str]:
    """A bid may only point at the bidder's own portfolio items (no duplicates)."""
    if len(set(item_ids)) != len(item_ids):
        raise DomainError(
            "Each portfolio item can be attached once.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"portfolio_item_ids": "duplicate item"},
        )
    owned = await repo.owned_portfolio_ids(ctx.db, ctx.uid, item_ids)
    if owned != set(item_ids):
        raise DomainError(
            "Attach items from your own portfolio.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"portfolio_item_ids": "not one of your portfolio items"},
        )
    return [str(x) for x in item_ids]


async def _bid_context(db: AsyncSession, bids: Sequence[Bid]) -> dict[uuid.UUID, tuple[str, str]]:
    """(project title, slot name) per bid id, in one query (the developer can read both)."""
    if not bids:
        return {}
    rows = await db.execute(
        select(Bid.id, Project.title, ProjectSlot.label, Skill.name)
        .join(Project, Project.id == Bid.project_id)
        .join(ProjectSlot, ProjectSlot.id == Bid.slot_id)
        .join(Skill, Skill.id == ProjectSlot.skill_id)
        .where(Bid.id.in_([b.id for b in bids]))
    )
    return {bid_id: (title, label or skill) for bid_id, title, label, skill in rows}


def _bid_out(bid: Bid, context: dict[uuid.UUID, tuple[str, str]]) -> BidOut:
    title, slot_name = context.get(bid.id, ("Project", "Slot"))
    return BidOut(
        id=bid.id,
        project_id=bid.project_id,
        project_title=title,
        slot_id=bid.slot_id,
        slot_label=slot_name,
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
    portfolio = await _check_portfolio(ctx, body.portfolio_item_ids)
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
        portfolio_item_ids=portfolio,
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
    await marketplace.forget_recommendations(ctx.uid)
    return _bid_out(bid, await _bid_context(ctx.db, [bid]))


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
    if body.portfolio_item_ids is not None:
        bid.portfolio_item_ids = await _check_portfolio(ctx, body.portfolio_item_ids)
    await write_audit(
        ctx.db, action="bid.update", entity_type="bid", entity_id=bid.id, actor_id=ctx.uid
    )
    await ctx.db.commit()
    await ctx.db.refresh(bid)
    return _bid_out(bid, await _bid_context(ctx.db, [bid]))


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
    await marketplace.forget_recommendations(ctx.uid)


async def my_bids(ctx: Ctx) -> list[BidOut]:
    bids = list(await repo.list_for_developer(ctx.db, ctx.uid))
    context = await _bid_context(ctx.db, bids)
    return [_bid_out(b, context) for b in bids]


# --------------------------------------------------------------------------- check text


def _pct(score: float) -> str:
    return f"{score * 100:.0f}"


def _check_out(check: Check, skill: str) -> ConstraintCheck:
    """Human text for one Algorithm 1 check (scores shown ×100, money as ৳)."""
    req, act = check.required, check.actual
    match check.name:
        case "account_active":
            detail = "Account active" if check.ok else "Account not active"
        case "has_slot_skill":
            detail = f"Lists {skill}" if check.ok else f"Doesn't list {skill}"
        case "no_conflict":
            detail = "No conflict of interest" if check.ok else "Conflict of interest"
        case "available":
            detail = (
                "Enough free hours over the project period"
                if check.ok
                else "Not enough free hours over the project period"
            )
        case "skill_evidence":
            detail = (
                f"No {skill} test result (newcomers need {_pct(float(req or 0))}%)"
                if act is None
                else f"{skill} test {_pct(float(act))}% (newcomers need {_pct(float(req or 0))}%)"
            )
        case "performance":
            detail = f"Performance {_pct(float(act or 0))} (minimum {_pct(float(req or 0))})"
        case "competency":
            detail = f"Competency {_pct(float(act or 0))} (minimum {_pct(float(req or 0))})"
        case "days":
            detail = f"{act} days (deadline {req} days)"
        case "price":
            detail = f"{format_taka(int(act or 0))} (budget after fee {format_taka(int(req or 0))})"
        case _:
            detail = check.name
    return ConstraintCheck(
        name=check.name,
        ok=check.ok,
        detail=detail,
        required=float(req) if req is not None else None,
        actual=float(act) if act is not None else None,
    )


async def _skill_names(db: AsyncSession, skill_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not skill_ids:
        return {}
    rows = await db.execute(select(Skill.id, Skill.name).where(Skill.id.in_(skill_ids)))
    return dict(rows.tuples().all())


# --------------------------------------------------------------------------- eligibility preview


async def eligibility_preview(
    ctx: Ctx, project_id: uuid.UUID, body: EligibilityIn
) -> EligibilityOut:
    """Dry-run one draft bid against the project's own constraints. It never ranks the bid
    against other (sealed) bids, so NOT_SHORTLISTED can't appear here (§14.5)."""
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
    terms = project_terms(project, list(slots.values()), settings)
    rep = await reputation_read.read_one(ctx.db, ctx.uid, settings)
    data = await _bidder_data(ctx.db, [ctx.uid], project.id)
    bid = _bid_input(
        bid_id="preview",
        developer_id=ctx.uid,
        slot=slot,
        rep=rep,
        data=data,
        days=body.days_needed,
        price=body.price_paisa,
        commitment=await _default_hours(ctx, body.hours_per_week_committed),
        period=_period(project, ctx.now.date()),
        active=ctx.principal.is_active,
    )
    proj = _project_input(terms, project, list(slots.values()), settings.pay.platform_fee_bp)
    params = _params(settings, terms)
    reason = classify_bid(bid, proj, params, params.p0, params.c0)
    skill = (await _skill_names(ctx.db, [slot.skill_id])).get(slot.skill_id, "this skill")
    checks = [_check_out(c, skill) for c in explain_bid(bid, proj, params, params.p0, params.c0)]
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


# --------------------------------------------------------------------------- evaluation


@dataclass(frozen=True)
class Evaluation:
    """Algorithm 1 over a project's active bids, with everything the views need."""

    project: Project
    terms: Terms
    slots: list[ProjectSlot]
    bids: list[Bid]
    inputs: list[BidInput]
    result: FilterResult
    reps: dict[uuid.UUID, reputation_read.ReputationView]
    params: FilterParams
    proj: ProjectInput
    skill_names: dict[uuid.UUID, str]

    def slot_name(self, slot: ProjectSlot | None) -> str:
        """A slot's own label, or its skill's name when the client gave none."""
        if slot is None:
            return "Slot"
        return slot.label or self.skill_names.get(slot.skill_id, "Slot")


async def evaluate(
    db: AsyncSession,
    project: Project,
    settings: PlatformSettingsValues,
    today: date,
    terms: Terms | None = None,
) -> Evaluation:
    """Run Algorithm 1 over a project's active bids, optionally under changed `terms` (a
    what-if for the too-few-bids actions). Ctx-free so the deadline job can reuse it."""
    bids = list(await repo.list_active_for_project(db, project.id))
    slots = list(await projrepo.load_slots(db, project.id))
    terms = terms or project_terms(project, slots, settings)
    dev_ids = [b.developer_id for b in bids]
    reps = await reputation_read.read_many(db, dev_ids, settings)
    data = await _bidder_data(db, dev_ids, project.id)
    by_slot = {s.id: s for s in slots}
    period = _period(project, today)
    inputs = [
        _bid_input(
            bid_id=str(b.id),
            developer_id=b.developer_id,
            slot=by_slot.get(b.slot_id),
            rep=reps[b.developer_id],
            data=data,
            days=b.days_needed,
            price=b.price_paisa,
            commitment=b.hours_per_week_committed,
            period=period,
            active=True,
        )
        for b in bids
    ]
    proj = _project_input(terms, project, slots, settings.pay.platform_fee_bp)
    params = _params(settings, terms)
    return Evaluation(
        project=project,
        terms=terms,
        slots=slots,
        bids=bids,
        inputs=inputs,
        result=filter_bids(inputs, proj, params),
        reps=reps,
        params=params,
        proj=proj,
        skill_names=await _skill_names(db, [s.skill_id for s in slots]),
    )


async def evaluate_project(
    db: AsyncSession, project: Project, settings: PlatformSettingsValues, today: date
) -> tuple[list[Bid], FilterResult, dict[uuid.UUID, reputation_read.ReputationView]]:
    """Run Algorithm 1 over a project's active bids (deadline job and seed entry point)."""
    ev = await evaluate(db, project, settings, today)
    return ev.bids, ev.result, ev.reps


def coverage(ev: Evaluation) -> list[SlotCoverage]:
    """Places covered per slot, in slot-name order (stable for people and screenshots)."""
    eligible = set(ev.result.eligible)
    rows = [
        SlotCoverage(
            slot_id=s.id,
            slot_label=ev.slot_name(s),
            needed=ev.terms.slot_counts.get(s.id, s.count),
            eligible=sum(1 for b in ev.bids if b.slot_id == s.id and str(b.id) in eligible),
        )
        for s in ev.slots
    ]
    return sorted(rows, key=lambda c: (c.slot_label.casefold(), str(c.slot_id)))


def team_cost(ev: Evaluation) -> TeamCostOut:
    cost = cheapest_team_cost(ev.inputs, set(ev.result.eligible), ev.proj)
    return TeamCostOut(
        total_paisa=cost.total_paisa,
        budget_after_fee_paisa=cost.budget_after_fee_paisa,
        complete=cost.complete,
    )


# --------------------------------------------------------------------------- client bids view


async def client_bids(ctx: Ctx, project_id: uuid.UUID) -> ClientBidsOut:
    project = await _own_project(ctx, project_id)
    return await bids_view(ctx, project)


async def bids_view(ctx: Ctx, project: Project) -> ClientBidsOut:
    """The client's view of every active bid with the Algorithm 1 verdict and its trace."""
    settings = await active_settings(ctx.db)
    # Eligibility needs each bidder's skills/evidence, which the client can't read directly;
    # evaluate in a SYSTEM session (the caller is already confirmed as the project's owner, and
    # only the verdict and its trace — not raw developer data — are returned). See D50. The view
    # is built inside the session: its ORM rows can't be read once it closes.
    async with open_session(DbContext.system(), job=True) as sysdb:
        ev = await evaluate(sysdb, project, settings, ctx.now.date())
        dev_ids = [b.developer_id for b in ev.bids]
        names = {
            u.id: u.display_name
            for u in await sysdb.scalars(select(User).where(User.id.in_(dev_ids)))
        }
        titles = await repo.portfolio_titles(
            sysdb, [uuid.UUID(str(x)) for b in ev.bids for x in b.portfolio_item_ids]
        )
        # Slot by slot; within a slot eligible bids first, then cheapest (stable order).
        rows = sorted(
            _client_rows(ev, names, titles),
            key=lambda r: (
                r.slot_label.casefold(),
                not r.eligible,
                r.price_paisa,
                r.developer_name,
                str(r.id),
            ),
        )
        coverage_out = coverage(ev)
        cost = team_cost(ev)
    result = ev.result
    used_p0 = result.relaxations[-1].p0 if result.relaxations else ev.params.p0
    used_c0 = result.relaxations[-1].c0 if result.relaxations else ev.params.c0
    default_p0, default_c0 = default_thresholds(settings)
    floor_p0, floor_c0 = threshold_floor(settings)
    return ClientBidsOut(
        bids=rows,
        coverage=coverage_out,
        relaxations=[RelaxationOut(step=r.step, p0=r.p0, c0=r.c0) for r in result.relaxations],
        too_few=result.too_few,
        evaluated_at=ctx.now,
        thresholds=Thresholds(
            p0=ev.params.p0,
            c0=ev.params.c0,
            default_p0=default_p0,
            default_c0=default_c0,
            floor_p0=floor_p0,
            floor_c0=floor_c0,
            used_p0=used_p0,
            used_c0=used_c0,
        ),
        team_cost=cost,
        budget_paisa=project.budget_paisa,
        team_size=project.team_size,
        bidding=BiddingWindow(
            deadline=project.bidding_deadline,
            closed=bidding_closed(project, ctx.now),
            extensions_used=project.bidding_extensions,
            max_extensions=settings.bidding.max_extensions,
            extend_days=settings.bidding.extend_days,
            closes_automatically_at=auto_close_at(project) if result.too_few else None,
        ),
    )


def _client_rows(
    ev: Evaluation, names: dict[uuid.UUID, str], titles: dict[uuid.UUID, str]
) -> list[ClientBidOut]:
    result = ev.result
    rejected = dict(result.rejected)
    eligible = set(result.eligible)
    not_shortlisted = set(result.not_shortlisted)
    used_p0 = result.relaxations[-1].p0 if result.relaxations else ev.params.p0
    used_c0 = result.relaxations[-1].c0 if result.relaxations else ev.params.c0
    slots = {s.id: s for s in ev.slots}
    newcomer_rule = ev.params.mode is Mode.DEVSYNC
    rows: list[ClientBidOut] = []
    for b, inp in zip(ev.bids, ev.inputs, strict=True):
        bid_id = str(b.id)
        reasons: list[str] = []
        if bid_id in rejected:
            reasons = [rejected[bid_id].value]
        elif bid_id in not_shortlisted:
            reasons = [ReasonCode.NOT_SHORTLISTED.value]
        rep = ev.reps[b.developer_id]
        slot = slots.get(b.slot_id)
        skill = ev.skill_names.get(slot.skill_id, "this skill") if slot else "this skill"
        evidence = (
            NewcomerEvidence(skill=skill, score=inp.skill_evidence_score)
            if newcomer_rule and rep.is_newcomer and inp.skill_evidence_score is not None
            else None
        )
        item_ids = [uuid.UUID(str(x)) for x in b.portfolio_item_ids]
        rows.append(
            ClientBidOut(
                id=b.id,
                developer_id=b.developer_id,
                developer_name=names.get(b.developer_id, "Developer"),
                slot_id=b.slot_id,
                slot_label=ev.slot_name(slot),
                status=b.status.value,
                price_paisa=b.price_paisa,
                days_needed=b.days_needed,
                hours_per_week=b.hours_per_week_committed,
                competency=rep.c,
                teamwork=rep.xm,
                performance=rep.p,
                is_newcomer=rep.is_newcomer,
                seeded=rep.seeded,
                eligible=bid_id in eligible,
                shortlisted=bid_id in eligible and bid_id not in not_shortlisted,
                reasons=reasons,
                checks=[
                    _check_out(c, skill)
                    for c in explain_bid(inp, ev.proj, ev.params, used_p0, used_c0)
                ],
                newcomer_evidence=evidence,
                proposal=b.proposal,
                expected_contribution=b.expected_contribution,
                portfolio=[PortfolioRef(id=i, title=titles[i]) for i in item_ids if i in titles],
                submitted_at=b.created_at,
            )
        )
    return rows
