"""Performance budgets for team formation (spec §9.3, §9.4, §16.5 step 16): binary PSO with
|S| = 200 candidates and N = 10 (P = 30, I = 200) in under 5 s, and the exact solver on 18
candidates in under 3 s. Median of 3 runs, so one scheduler hiccup can't fail it."""

from __future__ import annotations

import statistics
import time

import pytest

from app.algorithms.bpso import PsoParams, run_bpso
from app.algorithms.exact_solver import solve_exact
from app.algorithms.formation_bench import random_instance

pytestmark = pytest.mark.perf


def _median_seconds(fn: object, runs: int = 3) -> float:
    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()  # type: ignore[operator]
        timings.append(time.perf_counter() - start)
    return statistics.median(timings)


def test_pso_200_candidates_team_of_10_under_5s() -> None:
    p = random_instance(7, candidates=200, slots=9)  # s0 holds two places: N = 10
    assert p.size == 200
    assert p.team_size == 10
    result = run_bpso(p, PsoParams(), 7)
    assert result.feasible
    assert _median_seconds(lambda: run_bpso(p, PsoParams(), 7)) < 5.0


def test_exact_solver_18_candidates_under_3s() -> None:
    p = random_instance(8, candidates=18, slots=3)
    assert p.size == 18
    assert solve_exact(p).available
    assert _median_seconds(lambda: solve_exact(p)) < 3.0
