"""Fairness dial and cost of fairness (spec §9.5, ours). PURE.

The optimiser runs twice on the same shortlist with the same seed: once with no newcomer minimum
(fitness F0, team T0) and once with the client's minimum k (Fk, Tk).

    cost of fairness = (F0 − Fk) / |F0|      0 when F0 ≤ 0 or the minimum was not binding

"Not binding" means T0 already had k or more newcomers, so both runs found the same best team.
Also reported: the price difference Σc(Tk) − Σc(T0) and the newcomers included. When no feasible
team has k newcomers, the largest feasible k below it is used and the reason says so (§9.5).
`pcs_replication` has no fairness dial: k is forced to 0 there.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from app.algorithms.fitness import NEG_INF, Problem

# A solver returns (team indices, fitness); −∞ and () when nothing is feasible.
Solver = Callable[[Problem], tuple[tuple[int, ...], float]]


@dataclass(frozen=True)
class FairnessResult:
    requested_k: int
    applied_k: int
    team: tuple[int, ...]  # Tk (the recommended team)
    fitness: float  # Fk
    baseline_team: tuple[int, ...]  # T0
    baseline_fitness: float  # F0
    cost: float  # cost of fairness, ≥ 0
    binding: bool
    price_difference_paisa: int  # Σc(Tk) − Σc(T0)
    newcomers: tuple[int, ...]  # newcomer indices in Tk
    reason: str | None  # set when applied_k < requested_k (MAX_FEASIBLE_K)


def _price(problem: Problem, team: tuple[int, ...]) -> int:
    return sum(problem.candidates[i].price_paisa for i in team)


def cost_of_fairness(f0: float, fk: float, binding: bool) -> float:
    """(F0 − Fk)/|F0|, 0 when F0 ≤ 0 or not binding; never negative."""
    if not binding or f0 <= 0 or NEG_INF in (fk, f0):
        return 0.0
    return max(0.0, (f0 - fk) / abs(f0))


def apply_fairness(problem: Problem, k: int, solve: Solver) -> FairnessResult:
    """Run the dial. `solve` is the optimiser (exact when available, else PSO, same seed)."""
    if k < 0:
        raise ValueError("k must not be negative")
    requested = 0 if problem.replication else k
    t0, f0 = solve(replace(problem, min_newcomers=0))
    newcomers_t0 = sum(problem.candidates[i].newcomer for i in t0)

    def with_k(kk: int) -> tuple[tuple[int, ...], float]:
        # T0 already meets the minimum: the constraint is not binding, same team.
        if newcomers_t0 >= kk and f0 > NEG_INF:
            return t0, f0
        return solve(replace(problem, min_newcomers=kk))

    applied = requested
    tk, fk = with_k(applied)
    reason = None
    while fk == NEG_INF and applied > 0:
        applied -= 1
        reason = "MAX_FEASIBLE_K"
        tk, fk = with_k(applied)
    binding = applied > newcomers_t0 and tk != t0
    return FairnessResult(
        requested_k=requested,
        applied_k=applied,
        team=tk,
        fitness=fk,
        baseline_team=t0,
        baseline_fitness=f0,
        cost=cost_of_fairness(f0, fk, binding),
        binding=binding,
        price_difference_paisa=_price(problem, tk) - _price(problem, t0),
        newcomers=tuple(i for i in tk if problem.candidates[i].newcomer),
        reason=reason,
    )
