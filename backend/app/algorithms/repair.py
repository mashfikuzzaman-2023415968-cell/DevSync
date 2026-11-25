"""Team repair (spec §9.9; DECISIONS D128, D129, D138). PURE.

When a member declines, lets the invitation expire, leaves or is removed, the remaining active
members are locked and each candidate for the open slot is tried in their place:

1. candidates are pre-ranked by their own marginal score (the member's fitness terms, Eq. 17) and
   the best `prefilter` (10) are evaluated;
2. for each, the best feasible team with the remaining members and that candidate forced in is
   found with the injected solver (the exact solver honours `Problem.locked`), so budget (C after
   the fee, A10), slot counts and the newcomer minimum all apply;
3. the top `top` (3) by fitness are returned.

The newcomer minimum is kept when a newcomer candidate exists for the slot; otherwise it is relaxed
to what the remaining team already has, with a note. With no feasible candidate the reasons are
`NO_BIDS_FOR_SLOT` (nobody to try), `REMAINING_BUDGET_TOO_LOW` (with the smallest shortfall in
paisa) or `NONE_AVAILABLE` (the service passes how many were dropped as unavailable).

`repair_impact` estimates the project impact of a candidate (D138): every affected milestone
(D129) has its duration scaled by candidate days ÷ departed member's days (rounded up, ≥ 1), CPM
is recomputed, and the delay is the new duration minus the baseline's; the budget delta is the
team's price with the candidate minus C.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from app.algorithms.cpm import MilestoneInput, compute_cpm
from app.algorithms.fitness import NEG_INF, Infeasible, Problem, infeasibility

Solver = Callable[[Problem], tuple[tuple[int, ...], float]]

NO_BIDS_FOR_SLOT = "NO_BIDS_FOR_SLOT"
REMAINING_BUDGET_TOO_LOW = "REMAINING_BUDGET_TOO_LOW"
NONE_AVAILABLE = "NONE_AVAILABLE"
NEWCOMER_MINIMUM_RELAXED = "NEWCOMER_MINIMUM_RELAXED"


@dataclass(frozen=True)
class RankedCandidate:
    index: int  # candidate index in the problem
    team: tuple[int, ...]
    fitness: float
    price_paisa: int  # the whole team's price


@dataclass(frozen=True)
class RepairResult:
    candidates: tuple[RankedCandidate, ...]  # best first, at most `top`
    reasons: tuple[str, ...]  # why there are none (empty when there are some)
    shortfall_paisa: int | None  # REMAINING_BUDGET_TOO_LOW: the least extra budget needed
    notes: tuple[str, ...]  # e.g. NEWCOMER_MINIMUM_RELAXED
    min_newcomers: int  # the minimum actually applied


def rank_replacements(
    problem: Problem,
    remaining: frozenset[int],
    pool: Sequence[int],
    solve: Solver,
    *,
    unavailable: int = 0,
    prefilter: int = 10,
    top: int = 3,
) -> RepairResult:
    """Rank the candidates in `pool` (indices of `problem.candidates`) for the open place."""
    notes: list[str] = []
    have = sum(problem.candidates[i].newcomer for i in remaining)
    k = problem.min_newcomers
    if k > have and not any(problem.candidates[i].newcomer for i in pool):
        k = have
        notes.append(NEWCOMER_MINIMUM_RELAXED)
    base = replace(problem, min_newcomers=k)
    if not pool:
        reasons = [NONE_AVAILABLE] if unavailable else [NO_BIDS_FOR_SLOT]
        return RepairResult((), tuple(reasons), None, tuple(notes), k)
    ordered = sorted(pool, key=lambda i: (-base.terms(i).total, i))[:prefilter]
    ranked: list[RankedCandidate] = []
    shortfall: int | None = None
    for i in ordered:
        team, fit = solve(replace(base, locked=remaining | {i}))
        if fit > NEG_INF and team:
            price = sum(base.candidates[j].price_paisa for j in team)
            ranked.append(RankedCandidate(i, tuple(sorted(team)), fit, price))
            continue
        # Why not: when the obvious team (remaining + i) is over budget, record the gap.
        obvious = tuple(sorted(remaining | {i}))
        if infeasibility(base, obvious) is Infeasible.OVER_BUDGET:
            gap = sum(base.candidates[j].price_paisa for j in obvious)
            gap -= base.budget_after_fee_paisa
            shortfall = gap if shortfall is None else min(shortfall, gap)
    ranked.sort(key=lambda r: (-r.fitness, r.index))
    if ranked:
        return RepairResult(tuple(ranked[:top]), (), None, tuple(notes), k)
    reasons = []
    if shortfall is not None:
        reasons.append(REMAINING_BUDGET_TOO_LOW)
    if unavailable:
        reasons.append(NONE_AVAILABLE)
    return RepairResult((), tuple(reasons or [NO_BIDS_FOR_SLOT]), shortfall, tuple(notes), k)


@dataclass(frozen=True)
class PlanMilestone:
    id: str
    name: str
    duration_days: int
    predecessors: tuple[str, ...]
    skills: frozenset[str]
    done: bool = False


@dataclass(frozen=True)
class Impact:
    affected: tuple[str, ...]  # milestone ids
    baseline_days: int
    new_days: int
    delay_days: int  # new − baseline (negative: earlier)
    budget_delta_paisa: int  # team price with the candidate − C (A10); > 0 is over budget
    budget_only: bool  # no milestone lists the slot's skill (D129)


def affected_milestones(
    plan: Sequence[PlanMilestone], skill: str, *, started: bool
) -> tuple[str, ...]:
    """D129: milestones that list the departed member's slot skill (not yet done after start)."""
    return tuple(m.id for m in plan if skill in m.skills and not (started and m.done))


def repair_impact(
    plan: Sequence[PlanMilestone],
    skill: str,
    *,
    started: bool,
    departed_days: int,
    candidate_days: int,
    baseline_days: int,
    team_price_paisa: int,
    budget_after_fee_paisa: int,
) -> Impact:
    """D138: scale the affected milestones by candidate ÷ departed days and recompute CPM."""
    if departed_days < 1 or candidate_days < 1:
        raise ValueError("days must be at least 1")
    affected = affected_milestones(plan, skill, started=started)
    factor = candidate_days / departed_days
    adjusted = [
        MilestoneInput(
            id=m.id,
            duration_days=max(1, math.ceil(m.duration_days * factor - 1e-9))
            if m.id in affected
            else m.duration_days,
            predecessors=m.predecessors,
            name=m.name,
        )
        for m in plan
    ]
    new_days = compute_cpm(adjusted).duration if adjusted else 0
    return Impact(
        affected=affected,
        baseline_days=baseline_days,
        new_days=new_days,
        delay_days=new_days - baseline_days,
        budget_delta_paisa=team_price_paisa - budget_after_fee_paisa,
        budget_only=not affected,
    )
