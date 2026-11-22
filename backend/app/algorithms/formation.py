"""One team formation run, end to end (spec §9.2–§9.7). PURE: no clock, I/O or database.

The service freezes the inputs (candidate snapshot, parameters, seed) and calls `run_formation`;
re-running it with the same inputs gives the same outcome (FR-TEAM-6, D109), which is what the
admin "verify" action and the reproduction test check.

Steps:
1. The fairness dial (§9.5): binary PSO (Algorithm 2) with k = 0 and with the requested k (same
   seed), falling back to the largest feasible k; the recommended team is T_k.
2. Exact verification (§9.4) when the problem is within the solver's limits: "✓ Optimal" or the
   gap to the true best, plus the top three distinct teams for the comparison; otherwise the
   comparison uses the PSO archive.
3. "Why this team?" against the runner-up, with the §9.7 risk chips.

Progress goes through `on_progress(phase, iteration, best_fitness)`; the caller's timeout through
`should_stop` (checked once per PSO iteration). When time runs out the best feasible team found so
far is returned with `timed_out` set.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace

from app.algorithms.bpso import PsoParams, PsoResult, run_bpso
from app.algorithms.exact_solver import ExactLimits, ExactResult, solve_exact
from app.algorithms.explain import TeamSummary, WhyThisTeam, compare_teams, why_this_team
from app.algorithms.fairness import FairnessResult, apply_fairness
from app.algorithms.fitness import NEG_INF, Problem

OPTIMAL_TOLERANCE = 1e-9
Progress = Callable[[str, int, float], None]


@dataclass(frozen=True)
class Verification:
    available: bool  # the exact solver ran (problem within its limits)
    reason: str | None  # why not (TOO_MANY_CANDIDATES / TOO_MANY_COMBINATIONS)
    optimal: bool | None
    gap: float | None  # (F_exact − F_pso) / |F_exact|, ≥ 0
    exact_fitness: float | None
    feasible_count: int | None


@dataclass(frozen=True)
class FormationOutcome:
    feasible: bool
    team: tuple[int, ...]
    fitness: float
    fairness: FairnessResult
    pso: PsoResult  # the run that produced the recommended team
    verification: Verification
    top: tuple[TeamSummary, ...]
    why: WhyThisTeam | None
    timed_out: bool


def _verify(problem: Problem, fit: float, limits: ExactLimits) -> tuple[Verification, ExactResult]:
    exact = solve_exact(problem, limits)
    if not exact.available:
        return Verification(False, exact.reason, None, None, None, None), exact
    if exact.fitness == NEG_INF:
        return Verification(True, None, fit == NEG_INF, None, None, exact.feasible_count), exact
    gap = 0.0 if fit == NEG_INF else max(0.0, exact.fitness - fit)
    rel = 1.0 if fit == NEG_INF else gap / abs(exact.fitness) if exact.fitness else gap
    optimal = rel <= OPTIMAL_TOLERANCE
    return Verification(True, None, optimal, rel, exact.fitness, exact.feasible_count), exact


def run_formation(
    problem: Problem,
    params: PsoParams,
    seed: int,
    *,
    limits: ExactLimits | None = None,
    critical_skills: frozenset[str] = frozenset(),
    should_stop: Callable[[], bool] | None = None,
    on_progress: Progress | None = None,
) -> FormationOutcome:
    """Run the dial, verify, compare and explain. `problem.min_newcomers` is the requested k."""
    lim = limits or ExactLimits()
    runs: dict[int, PsoResult] = {}

    def solve(p: Problem) -> tuple[tuple[int, ...], float]:
        phase = f"k{p.min_newcomers}"

        def report(iteration: int, best: float) -> None:
            if on_progress is not None:
                on_progress(phase, iteration, best)

        result = run_bpso(p, params, seed, should_stop=should_stop, on_iteration=report)
        runs[p.min_newcomers] = result
        return result.team, result.fitness

    fair = apply_fairness(problem, problem.min_newcomers, solve)
    pso = runs.get(fair.applied_k) or runs[0]
    applied = replace(problem, min_newcomers=fair.applied_k)
    verification, exact = _verify(applied, fair.fitness, lim)
    feasible = fair.fitness > NEG_INF
    candidates = list(exact.top) if exact.available else list(pso.archive)
    if feasible:
        candidates.append((tuple(sorted(fair.team)), fair.fitness))
    top = compare_teams(applied, candidates)
    team = tuple(sorted(fair.team)) if feasible else ()
    runner = next((t.team for t in top if t.team != team), None)
    why = why_this_team(applied, team, runner, critical_skills) if feasible else None
    return FormationOutcome(
        feasible=feasible,
        team=team,
        fitness=fair.fitness,
        fairness=fair,
        pso=pso,
        verification=verification,
        top=top,
        why=why,
        timed_out=any(r.timed_out for r in runs.values()),
    )


def finite(value: float) -> float | None:
    """A fitness for JSON: None for ±∞ (infeasible), else the number."""
    return value if math.isfinite(value) else None
