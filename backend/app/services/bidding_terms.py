"""Too-few-bids actions (spec §9.19): lower the standards, raise the budget, reduce the team.

The client can change these terms only while the project is `BIDDING` (before or after the
bidding deadline — after it the project waits in `BIDDING` until the shortfall is fixed). Every
change is previewed first: `preview()` re-runs Algorithm 1 under the proposed terms without
saving and reports the eligible count, coverage and cheapest team before and after.

Rules (DECISIONS D54), all checked here and tested:
- minimum standards stay within [platform default − full automatic relaxation, default]
  (P 30–45, C 25–40 by default), so a client can't switch the filter off; raising them back is
  allowed (undo);
- the budget can only go up;
- slot counts can only go down, never below 1 per slot or 2 per team (team_size bounds);
- at least one value must actually change.
Once bids exist, these actions (plus extend and cancel) are the **only** way to change the
budget, standards or team — the project itself is no longer editable (§8). Each applied change
bumps the project version (If-Match), is audited with before/after values, notifies every active
bidder (their eligibility may have changed) and, when bidding already closed and the team is now
covered, moves the project to `FORMING` like the deadline job would.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from decimal import Decimal
from typing import Any

from app.core.audit import write_audit
from app.core.errors import DomainError, ErrorCode, NotFoundError
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.projects import Project, ProjectSlot, ProjectStatus
from app.repositories import bids as bidrepo
from app.repositories import projects as projrepo
from app.schemas.bids import ClientBidsOut, TermsChange, TermsOutcome, TermsPreviewOut
from app.schemas.platform_settings import PlatformSettingsValues
from app.services import bids as bids_svc
from app.services.context import Ctx
from app.services.notifications import notify_users

MIN_TEAM = 2
TERMS_CHANGED = "PROJECT_TERMS_CHANGED"


async def _own_bidding_project(
    ctx: Ctx, project_id: uuid.UUID, if_match: int | None = None
) -> Project:
    project = await projrepo.get_project(ctx.db, project_id)
    if project is None or project.client_id != ctx.uid:
        raise NotFoundError
    if project.status != ProjectStatus.BIDDING:
        raise DomainError(
            "These changes are only possible while the project is open for bids.",
            code=ErrorCode.INVALID_STATE,
        )
    if if_match is not None and project.version != if_match:
        raise DomainError(
            "This project changed since you loaded it. Reload and try again.",
            code=ErrorCode.VERSION_CONFLICT,
        )
    return project


def _bad(field: str, message: str, detail: str) -> DomainError:
    return DomainError(message, code=ErrorCode.VALIDATION_ERROR, fields={field: detail})


def _new_terms(
    current: bids_svc.Terms,
    slots: list[ProjectSlot],
    change: TermsChange,
    settings: PlatformSettingsValues,
) -> bids_svc.Terms:
    """Validate a change against the rules above and return the resulting terms."""
    default_p, default_c = bids_svc.default_thresholds(settings)
    floor_p, floor_c = bids_svc.threshold_floor(settings)
    terms = current
    if change.min_performance is not None:
        p0 = float(change.min_performance)
        if not floor_p - 1e-9 <= p0 <= default_p + 1e-9:
            raise _bad(
                "min_performance",
                f"Minimum performance must stay between {floor_p * 100:.0f} and "
                f"{default_p * 100:.0f}.",
                "out of range",
            )
        terms = replace(terms, p0=p0)
    if change.min_competency is not None:
        c0 = float(change.min_competency)
        if not floor_c - 1e-9 <= c0 <= default_c + 1e-9:
            raise _bad(
                "min_competency",
                f"Minimum competency must stay between {floor_c * 100:.0f} and "
                f"{default_c * 100:.0f}.",
                "out of range",
            )
        terms = replace(terms, c0=c0)
    if change.budget_paisa is not None:
        if change.budget_paisa < current.budget_paisa:
            raise _bad(
                "budget_paisa", "The budget can only be raised.", "lower than the current budget"
            )
        terms = replace(terms, budget_paisa=change.budget_paisa)
    if change.slot_counts is not None:
        known = {s.id: s for s in slots}
        counts = dict(current.slot_counts)
        seen: set[uuid.UUID] = set()
        for item in change.slot_counts:
            if item.slot_id not in known or item.slot_id in seen:
                raise _bad("slot_counts", "Choose this project's slots, once each.", "unknown slot")
            seen.add(item.slot_id)
            if item.count > current.slot_counts[item.slot_id]:
                raise _bad(
                    "slot_counts",
                    "The team can only be reduced here; add places by re-planning instead.",
                    "count above the current one",
                )
            counts[item.slot_id] = item.count
        if sum(counts.values()) < MIN_TEAM:
            raise _bad("slot_counts", f"A team needs at least {MIN_TEAM} people.", "team too small")
        terms = replace(terms, slot_counts=counts)
    if terms == current:
        raise _bad("terms", "Nothing would change.", "no change")
    return terms


def _outcome(ev: bids_svc.Evaluation) -> TermsOutcome:
    return TermsOutcome(
        eligible=len(ev.result.eligible),
        too_few=ev.result.too_few,
        coverage=bids_svc.coverage(ev),
        team_cost=bids_svc.team_cost(ev),
    )


def _message(before: TermsOutcome, after: TermsOutcome) -> str:
    gained = after.eligible - before.eligible
    if gained > 0:
        head = f"{gained} more bid{'s' if gained != 1 else ''} would be eligible"
    elif gained < 0:
        head = f"{-gained} fewer bid{'s' if gained != -1 else ''} would be eligible"
    else:
        head = "The number of eligible bids would not change"
    tail = (
        "every slot would be covered." if not after.too_few else "some slots would still be short."
    )
    return f"{head}; {tail}"


async def preview(ctx: Ctx, project_id: uuid.UUID, change: TermsChange) -> TermsPreviewOut:
    """What the change would do to the eligible set — nothing is saved."""
    project = await _own_bidding_project(ctx, project_id)
    settings = await active_settings(ctx.db)
    slots = list(await projrepo.load_slots(ctx.db, project_id))
    current = bids_svc.project_terms(project, slots, settings)
    proposed = _new_terms(current, slots, change, settings)
    async with open_session(DbContext.system(), job=True) as sysdb:
        before_ev = await bids_svc.evaluate(sysdb, project, settings, ctx.now.date(), current)
        after_ev = await bids_svc.evaluate(sysdb, project, settings, ctx.now.date(), proposed)
        # Built inside the session: the evaluations' ORM rows can't be read once it closes.
        before, after = _outcome(before_ev), _outcome(after_ev)
    newly = len(set(after_ev.result.eligible) - set(before_ev.result.eligible))
    return TermsPreviewOut(
        before=before, after=after, newly_eligible=newly, message=_message(before, after)
    )


def _audit_values(terms: bids_svc.Terms) -> dict[str, Any]:
    return {
        "min_performance": terms.p0,
        "min_competency": terms.c0,
        "budget_paisa": terms.budget_paisa,
        "slot_counts": {str(k): v for k, v in terms.slot_counts.items()},
    }


async def apply(
    ctx: Ctx, project_id: uuid.UUID, change: TermsChange, if_match: int | None
) -> ClientBidsOut:
    """Apply a validated change, audit it, notify bidders and return the fresh bids view."""
    project = await _own_bidding_project(ctx, project_id, if_match)
    settings = await active_settings(ctx.db)
    slots = list(await projrepo.load_slots(ctx.db, project_id))
    current = bids_svc.project_terms(project, slots, settings)
    new = _new_terms(current, slots, change, settings)

    default_p, default_c = bids_svc.default_thresholds(settings)
    if new.p0 != current.p0:
        project.min_performance = None if new.p0 == default_p else Decimal(f"{new.p0:.2f}")
    if new.c0 != current.c0:
        project.min_competency = None if new.c0 == default_c else Decimal(f"{new.c0:.2f}")
    project.budget_paisa = new.budget_paisa
    for slot in slots:
        slot.count = new.slot_counts[slot.id]
    project.team_size = sum(new.slot_counts.values())
    project.version += 1
    await write_audit(
        ctx.db,
        action="project.terms_changed",
        entity_type="project",
        entity_id=project.id,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        before=_audit_values(current),
        after=_audit_values(new),
    )
    await ctx.db.commit()
    await ctx.db.refresh(project)

    bidders = await bidrepo.active_bidder_ids(ctx.db, project.id)
    await notify_users(
        bidders,
        TERMS_CHANGED,
        title="A project you bid on changed its terms",
        body=f"The client updated the budget, minimum standards or team size of "
        f"“{project.title}”. Your bid's eligibility may have changed.",
        link="/dev/bids",
    )
    view = await bids_svc.bids_view(ctx, project)
    if view.bidding.closed and not view.too_few:
        # Bidding already closed short of bids; the change fixed it, so form the team now.
        project.status = ProjectStatus.FORMING
        project.version += 1
        await write_audit(
            ctx.db,
            action="project.bidding_closed",
            entity_type="project",
            entity_id=project.id,
            actor_id=ctx.uid,
            actor_role=ctx.principal.role,
            after={"status": ProjectStatus.FORMING.value},
        )
        await ctx.db.commit()
    return view
