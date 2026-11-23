"""Explanations of a formation result (spec §9.6–§9.8, ours). PURE.

- `team_risks` — the §9.7 chips with their exact thresholds: `BUDGET_TIGHT` (Σ price > 95 % of
  C), `SCHEDULE_TIGHT` (max t > 90 % of T^d), `LOW_TEAMWORK` (mean X_m < 0.5),
  `SINGLE_POINT_SKILL` (a skill a critical milestone needs is held by exactly one member) and
  `NEWCOMER_ON_CRITICAL_PATH` (informational).
- `why_this_team` — coverage per slot, budget and schedule against their limits, newcomers, each
  member's contribution by term, and how the runner-up differs (which terms made the difference).
- `compare_teams` — the top teams side by side (§9.6).
- `why_not_selected` — for an eligible bid that wasn't chosen: the best team that includes it
  (forced inclusion) and its gap to the recommended team, the highest price at which it would
  have been selected (10-step binary search on φ ∈ [0.5, 1], rounded down to ৳100), and the main
  gap against the selected member in the same slot, as a term the UI turns into a hint (§9.8).

Solvers are injected (exact when the problem is small, PSO otherwise), so this module stays pure.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from app.algorithms.fitness import NEG_INF, Breakdown, Problem, breakdown, fitness

Solver = Callable[[Problem], tuple[tuple[int, ...], float]]

BUDGET_TIGHT_SHARE = 0.95
SCHEDULE_TIGHT_SHARE = 0.9
LOW_TEAMWORK_MEAN = 0.5
COUNTERFACTUAL_STEPS = 10
COUNTERFACTUAL_FLOOR = 0.5
ROUND_TO_PAISA = 10_000  # ৳100
TERMS = ("comp", "team", "time", "cost")


class Risk(enum.StrEnum):
    SINGLE_POINT_SKILL = "SINGLE_POINT_SKILL"
    BUDGET_TIGHT = "BUDGET_TIGHT"
    SCHEDULE_TIGHT = "SCHEDULE_TIGHT"
    LOW_TEAMWORK = "LOW_TEAMWORK"
    NEWCOMER_ON_CRITICAL_PATH = "NEWCOMER_ON_CRITICAL_PATH"


def team_risks(
    problem: Problem, team: Sequence[int], critical_skills: frozenset[str] = frozenset()
) -> tuple[Risk, ...]:
    """The §9.7 risk chips for a team, in a fixed order."""
    members = [problem.candidates[i] for i in team]
    if not members:
        return ()
    risks: list[Risk] = []
    for skill in sorted(critical_skills):
        if sum(skill in m.skills for m in members) == 1:
            risks.append(Risk.SINGLE_POINT_SKILL)
            break
    if sum(m.price_paisa for m in members) > BUDGET_TIGHT_SHARE * problem.budget_after_fee_paisa:
        risks.append(Risk.BUDGET_TIGHT)
    if max(m.days for m in members) > SCHEDULE_TIGHT_SHARE * problem.deadline_days:
        risks.append(Risk.SCHEDULE_TIGHT)
    if sum(m.teamwork for m in members) / len(members) < LOW_TEAMWORK_MEAN:
        risks.append(Risk.LOW_TEAMWORK)
    if any(m.newcomer and m.skills & critical_skills for m in members):
        risks.append(Risk.NEWCOMER_ON_CRITICAL_PATH)
    return tuple(risks)


@dataclass(frozen=True)
class TeamSummary:
    """One team as the comparison table and the stat row show it (§9.6)."""

    team: tuple[int, ...]
    fitness: float
    price_paisa: int
    newcomers: int
    mean_competency: float
    mean_teamwork: float
    max_days: int
    extra_skills: frozenset[str]  # skills held beyond the required ones
    covers_required: bool


def summarise(problem: Problem, team: Sequence[int], fit: float | None = None) -> TeamSummary:
    members = [problem.candidates[i] for i in team]
    held: set[str] = set()
    for m in members:
        held |= m.skills
    n = max(len(members), 1)
    return TeamSummary(
        team=tuple(sorted(team)),
        fitness=fit if fit is not None else fitness(problem, team),
        price_paisa=sum(m.price_paisa for m in members),
        newcomers=sum(m.newcomer for m in members),
        mean_competency=sum(m.competency for m in members) / n,
        mean_teamwork=sum(m.teamwork for m in members) / n,
        max_days=max((m.days for m in members), default=0),
        extra_skills=frozenset(held - problem.required_skills),
        covers_required=problem.required_skills <= held,
    )


def compare_teams(
    problem: Problem, teams: Sequence[tuple[tuple[int, ...], float]]
) -> tuple[TeamSummary, ...]:
    """The top distinct teams (exact top 3, else the PSO archive), best first."""
    seen: set[tuple[int, ...]] = set()
    out = []
    for team, fit in sorted(teams, key=lambda tf: (-tf[1], tf[0])):
        key = tuple(sorted(team))
        if key in seen or fit == NEG_INF:
            continue
        seen.add(key)
        out.append(summarise(problem, key, fit))
    return tuple(out[:3])


@dataclass(frozen=True)
class WhyThisTeam:
    summary: TeamSummary
    slots: dict[str, tuple[str, ...]]  # slot id -> bid ids
    budget_share: float  # Σ price / C
    schedule_share: float  # max t / T^d
    contributions: tuple[Breakdown, ...]
    runner_up: TeamSummary | None
    runner_up_difference: dict[str, float]  # term -> (team − runner-up), summed over members
    deciding_term: str | None  # the term that favoured this team most over the runner-up
    risks: tuple[Risk, ...]


def _term_totals(problem: Problem, team: Sequence[int]) -> dict[str, float]:
    totals = dict.fromkeys(TERMS, 0.0)
    for i in team:
        t = problem.terms(i)
        totals["comp"] += t.comp
        totals["team"] += t.team
        totals["time"] += t.time
        totals["cost"] += t.cost
    return totals


def why_this_team(
    problem: Problem,
    team: Sequence[int],
    runner_up: Sequence[int] | None = None,
    critical_skills: frozenset[str] = frozenset(),
) -> WhyThisTeam:
    """The "Why this team?" panel (§9.7); relaxations and verification are added by the caller."""
    chosen = tuple(sorted(team))
    slots: dict[str, list[str]] = {s: [] for s in problem.slots}
    for i in chosen:
        slots[problem.candidates[i].slot_id].append(problem.candidates[i].bid_id)
    summary = summarise(problem, chosen)
    diff: dict[str, float] = {}
    deciding = None
    runner = None
    if runner_up:
        runner = summarise(problem, runner_up)
        ours, theirs = _term_totals(problem, chosen), _term_totals(problem, runner_up)
        diff = {k: ours[k] - theirs[k] for k in TERMS}
        best = max(TERMS, key=lambda k: (diff[k], -TERMS.index(k)))
        deciding = best if diff[best] > 0 else None
    return WhyThisTeam(
        summary=summary,
        slots={s: tuple(v) for s, v in slots.items()},
        budget_share=summary.price_paisa / problem.budget_after_fee_paisa,
        schedule_share=summary.max_days / problem.deadline_days,
        contributions=breakdown(problem, chosen),
        runner_up=runner,
        runner_up_difference=diff,
        deciding_term=deciding,
        risks=team_risks(problem, chosen, critical_skills),
    )


@dataclass(frozen=True)
class WhyNotSelected:
    bid_index: int
    forced_team: tuple[int, ...]  # best team that includes the bid (empty: none feasible)
    forced_fitness: float
    gap: float  # F* − F_b (≥ 0)
    counterfactual_price_paisa: int | None  # highest price that gets it selected, ৳100 steps
    main_gap: str | None  # comp / team / time / cost: the largest weighted gap
    compared_with: int | None  # the selected member in the same slot it was compared with


def _with_price(problem: Problem, i: int, price: int) -> Problem:
    cands = list(problem.candidates)
    cands[i] = replace(cands[i], price_paisa=price)
    return replace(problem, candidates=tuple(cands))


def price_counterfactual(
    problem: Problem, i: int, best_fitness: float, solve: Solver
) -> int | None:
    """The highest price (rounded down to ৳100) at which the best team that must include bid
    `i` scores strictly more than the recommended team: at that price a re-run selects it.
    Binary search on φ ∈ [0.5, 1] of the bid's price, 10 steps (§9.8). None when even half
    the price is not enough (or the bid can't be in any feasible team)."""
    price = problem.candidates[i].price_paisa

    def wins(phi: float) -> bool:
        forced = replace(_with_price(problem, i, math.floor(price * phi)), locked=frozenset({i}))
        return solve(forced)[1] > best_fitness

    if not wins(COUNTERFACTUAL_FLOOR):
        return None
    lo, hi = COUNTERFACTUAL_FLOOR, 1.0
    for _ in range(COUNTERFACTUAL_STEPS):
        mid = (lo + hi) / 2
        if wins(mid):
            lo = mid
        else:
            hi = mid
    candidate = (math.floor(price * lo) // ROUND_TO_PAISA) * ROUND_TO_PAISA
    # Rounding down only lowers the price, which only raises this bid's fitness (Eq. 18), so the
    # rounded price still wins; check it anyway and step down once more if a rounding edge bites.
    while candidate > 0 and not _wins_at(problem, i, candidate, best_fitness, solve):
        candidate -= ROUND_TO_PAISA
    return candidate if candidate > 0 else None


def _wins_at(problem: Problem, i: int, price: int, best: float, solve: Solver) -> bool:
    forced = replace(_with_price(problem, i, price), locked=frozenset({i}))
    return solve(forced)[1] > best


def main_gap(problem: Problem, i: int, team: Sequence[int]) -> tuple[str | None, int | None]:
    """The term with the largest weighted gap between the bid and the selected member of the
    same slot it compares best against (the one it lost to by the least)."""
    slot = problem.candidates[i].slot_id
    rivals = [j for j in team if problem.candidates[j].slot_id == slot]
    if not rivals:
        return None, None
    mine = problem.terms(i)
    rival = min(rivals, key=lambda j: (problem.terms(j).total, j))
    theirs = problem.terms(rival)
    gaps = {k: getattr(theirs, k) - getattr(mine, k) for k in TERMS}
    term = max(TERMS, key=lambda k: (gaps[k], -TERMS.index(k)))
    return (term if gaps[term] > 0 else None), rival


def why_not_selected(
    problem: Problem, i: int, team: Sequence[int], best_fitness: float, solve: Solver
) -> WhyNotSelected:
    """§9.8 for one eligible bid that is not in the recommended team."""
    if i in team:
        raise ValueError("the bid is in the recommended team")
    forced_team, forced_fit = solve(replace(problem, locked=frozenset({i})))
    gap = best_fitness - forced_fit if forced_fit > NEG_INF else math.inf
    term, rival = main_gap(problem, i, team)
    return WhyNotSelected(
        bid_index=i,
        forced_team=forced_team,
        forced_fitness=forced_fit,
        gap=max(0.0, gap),
        counterfactual_price_paisa=price_counterfactual(problem, i, best_fitness, solve),
        main_gap=term,
        compared_with=rival,
    )
