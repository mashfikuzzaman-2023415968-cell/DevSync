"""The greedy baseline (E3) and how DevSync's formation compares with it (§17 Phase 7 test 11)."""

from __future__ import annotations

import pytest

from app.algorithms.baselines import greedy_team
from app.algorithms.exact_solver import solve_exact
from app.algorithms.fitness import Candidate, Problem, Weights, fitness, infeasibility
from app.algorithms.formation_bench import random_instance

pytestmark = pytest.mark.unit
W = Weights(0.35, 0.25, 0.2, 0.2)


def test_greedy_takes_the_top_rated_per_slot_when_affordable() -> None:
    """Slot s1: A (C+P = 1.6) beats E (1.2); s2 has only B."""
    a = Candidate("A", "dA", "s1", 0.9, 0.5, 0.7, 10, 300_000, False)
    e = Candidate("E", "dE", "s1", 0.6, 0.5, 0.6, 10, 100_000, True)
    b = Candidate("B", "dB", "s2", 0.5, 0.5, 0.5, 10, 300_000, False)
    p = Problem((a, e, b), {"s1": 1, "s2": 1}, 30, 1_000_000, W)
    assert greedy_team(p) == (0, 2)


def test_greedy_skips_the_top_rated_when_the_budget_cannot_take_it() -> None:
    """A would leave too little for s2 (300,000 + 800,000 > 1,000,000), so E is taken."""
    a = Candidate("A", "dA", "s1", 0.9, 0.5, 0.7, 10, 300_000, False)
    e = Candidate("E", "dE", "s1", 0.6, 0.5, 0.6, 10, 100_000, True)
    b = Candidate("B", "dB", "s2", 0.5, 0.5, 0.5, 10, 800_000, False)
    p = Problem((a, e, b), {"s1": 1, "s2": 1}, 30, 1_000_000, W)
    assert greedy_team(p) == (1, 2)


def test_greedy_gives_up_when_nothing_fits() -> None:
    a = Candidate("A", "dA", "s1", 0.9, 0.5, 0.7, 10, 900_000, False)
    b = Candidate("B", "dB", "s2", 0.5, 0.5, 0.5, 10, 900_000, False)
    assert greedy_team(Problem((a, b), {"s1": 1, "s2": 1}, 30, 1_000_000, W)) == ()


def test_devsync_never_scores_below_greedy_and_includes_more_newcomers() -> None:
    """On 100 simulated jobs (no newcomer minimum for greedy, k = 1 for DevSync): DevSync's
    team always has fitness ≥ greedy's on the problem greedy is feasible for, and DevSync's
    newcomer share is at least greedy's on average."""
    dev_newcomers = greedy_newcomers = jobs = 0
    for seed in range(100):
        p = random_instance(seed)
        g = greedy_team(p)
        if not g:
            continue
        plain = random_instance(seed, min_newcomers=0)
        if infeasibility(plain, g) is not None:
            continue
        best = solve_exact(plain).fitness
        assert best >= fitness(plain, g) - 1e-12, seed
        fair = solve_exact(p).best
        if not fair:
            continue
        jobs += 1
        dev_newcomers += sum(p.candidates[i].newcomer for i in fair)
        greedy_newcomers += sum(p.candidates[i].newcomer for i in g)
    assert jobs >= 80
    assert dev_newcomers >= greedy_newcomers
