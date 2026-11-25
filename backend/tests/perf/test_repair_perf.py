"""Performance budget for team repair (spec §9.9, §17 Phase 8): ranking 10 replacement candidates
for one place of a 4-member team takes under 5 s, both with the exact solver (small inputs) and
with binary PSO (the path for large ones). Median of 3 runs."""

from __future__ import annotations

import random
import statistics
import time
from dataclasses import replace

import pytest

from app.algorithms.bpso import PsoParams, run_bpso
from app.algorithms.exact_solver import solve_exact
from app.algorithms.fitness import Candidate, Problem
from app.algorithms.formation_bench import random_instance
from app.algorithms.repair import rank_replacements

pytestmark = pytest.mark.perf
SLOTS = ("s0", "s1", "s2", "s3")


def _instance(seed: int) -> Problem:
    """Three kept members (s0–s2) and ten bids for the open place s3."""
    rng = random.Random(seed)
    cands = [
        Candidate(bid_id=f"b{i:02d}", developer_id=f"d{i:02d}", slot_id=slot,
                  competency=rng.uniform(0.3, 0.95), teamwork=rng.uniform(0.3, 0.95),
                  performance=rng.uniform(0.4, 0.9), days=rng.randint(5, 30),
                  price_paisa=rng.randint(10, 40) * 100_000, newcomer=rng.random() < 0.3,
                  skills=frozenset({slot}))
        for i, slot in enumerate([*SLOTS[:3], *["s3"] * 10])
    ]  # fmt: skip
    base = random_instance(seed, candidates=4, slots=4)
    return replace(base, candidates=tuple(cands), slots=dict.fromkeys(SLOTS, 1),
                   budget_after_fee_paisa=20_000_000, min_newcomers=0,
                   required_skills=frozenset(SLOTS))  # fmt: skip


def _median_seconds(fn: object, runs: int = 3) -> float:
    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()  # type: ignore[operator]
        timings.append(time.perf_counter() - start)
    return statistics.median(timings)


def _exact(p: Problem) -> tuple[tuple[int, ...], float]:
    r = solve_exact(p)
    return r.best, r.fitness


def _pso(p: Problem) -> tuple[tuple[int, ...], float]:
    r = run_bpso(p, PsoParams(), 7)
    return r.team, r.fitness


@pytest.mark.parametrize("solve", [_exact, _pso], ids=["exact", "pso"])
def test_repair_10_candidates_4_members_under_5s(solve: object) -> None:
    p = _instance(11)
    kept, pool = frozenset({0, 1, 2}), list(range(3, 13))
    result = rank_replacements(p, kept, pool, solve)  # type: ignore[arg-type]
    assert len(result.candidates) == 3
    assert all(kept <= set(c.team) for c in result.candidates)
    seconds = _median_seconds(lambda: rank_replacements(p, kept, pool, solve))  # type: ignore[arg-type]
    assert seconds < 5.0
