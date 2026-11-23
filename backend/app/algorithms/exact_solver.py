"""Exact solver for small formation problems (spec §9.4, ours: verification). PURE.

Enumerates every team as the Cartesian product, over slots, of the combinations of that slot's
candidates of size `count` (C(n_s, k_s) each), evaluates Eq. 17 on the feasible ones and returns
the best, the top 3 distinct teams and how many feasible teams exist. It refuses — instead of
running for minutes — when the problem has more than `exact.max_candidates` (18) candidates or more
than `exact.max_combinations` (2,000,000) combinations. Used to verify small runs (the optimality
gap shown as "✓ Optimal"), by the admin "verify run" tool, for forced-inclusion questions in
"why not selected" (§9.8) and for experiment E1.

In `pcs_replication` the paper has no slots, so the enumeration is over all teams of size N
(combinations of all candidates), with the same limits.
"""

from __future__ import annotations

import heapq
import itertools
import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.algorithms.fitness import NEG_INF, Problem, fitness, infeasibility


@dataclass(frozen=True)
class ExactLimits:
    max_candidates: int = 18  # exact.max_candidates
    max_combinations: int = 2_000_000  # exact.max_combinations


@dataclass(frozen=True)
class ExactResult:
    available: bool  # False when the problem is over the limits (nothing was enumerated)
    reason: str | None  # TOO_MANY_CANDIDATES / TOO_MANY_COMBINATIONS
    best: tuple[int, ...]  # () when no feasible team exists
    fitness: float
    top: tuple[tuple[tuple[int, ...], float], ...]  # up to 3 distinct teams, best first
    feasible_count: int
    combinations: int


def combinations_count(problem: Problem) -> int:
    """How many teams the enumeration would look at."""
    if problem.replication:
        return math.comb(problem.size, problem.team_size)
    per_slot: dict[str, int] = dict.fromkeys(problem.slots, 0)
    for cand in problem.candidates:
        per_slot[cand.slot_id] += 1
    return math.prod(math.comb(per_slot[s], need) for s, need in problem.slots.items())


def _teams(problem: Problem) -> Iterable[tuple[tuple[int, ...], ...]]:
    if problem.replication:
        return [(t,) for t in itertools.combinations(range(problem.size), problem.team_size)]
    groups = []
    for slot, need in problem.slots.items():
        members = [i for i, c in enumerate(problem.candidates) if c.slot_id == slot]
        groups.append(itertools.combinations(members, need))
    return itertools.product(*groups)


def solve_exact(problem: Problem, limits: ExactLimits | None = None) -> ExactResult:
    """Best feasible team by full enumeration, or `available=False` over the limits."""
    lim = limits or ExactLimits()
    total = combinations_count(problem)
    if problem.size > lim.max_candidates:
        return ExactResult(False, "TOO_MANY_CANDIDATES", (), NEG_INF, (), 0, total)
    if total > lim.max_combinations:
        return ExactResult(False, "TOO_MANY_COMBINATIONS", (), NEG_INF, (), 0, total)
    locked = problem.locked
    heap: list[tuple[float, tuple[int, ...]]] = []  # min-heap of the best 3 (fitness, -index order)
    feasible = 0
    for parts in _teams(problem):
        team = tuple(sorted(i for part in parts for i in part))
        if not locked <= set(team) or infeasibility(problem, team) is not None:
            continue
        feasible += 1
        f = fitness(problem, team)
        # Ties prefer the lexicographically smaller team (deterministic, like PSO's tie-break).
        entry = (f, tuple(-i for i in team))
        if len(heap) < 3:  # noqa: PLR2004 - "top 3" (§9.4)
            heapq.heappush(heap, entry)
        elif entry > heap[0]:
            heapq.heapreplace(heap, entry)
    ranked = sorted(heap, reverse=True)
    top = tuple((tuple(-i for i in neg), f) for f, neg in ranked)
    best, best_f = top[0] if top else ((), NEG_INF)
    return ExactResult(True, None, best, best_f, top, feasible, total)
