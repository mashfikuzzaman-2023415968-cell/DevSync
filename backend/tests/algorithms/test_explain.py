"""Explanations are correct, not just present (spec §9.6–§9.8, §17 Phase 7 tests): risk chips at
their exact boundaries, "why this team" numbers, the comparison, the main gap, and the price
counterfactual — applied and re-run, it really selects the bid."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.algorithms.exact_solver import solve_exact
from app.algorithms.explain import (
    Risk,
    compare_teams,
    main_gap,
    price_counterfactual,
    summarise,
    team_risks,
    why_not_selected,
    why_this_team,
)
from app.algorithms.fitness import Candidate, Problem, Weights
from app.algorithms.formation_bench import random_instance

pytestmark = pytest.mark.unit


def exact(problem: Problem) -> tuple[tuple[int, ...], float]:
    r = solve_exact(problem)
    return r.best, r.fitness


def _two(price_a: int = 400_000, price_b: int = 500_000, days: int = 20, xm: float = 0.6,
         budget: int = 1_000_000) -> Problem:  # fmt: skip
    a = Candidate("A", "dA", "s1", 0.7, xm, 0.6, days, price_a, False, frozenset({"react"}))
    b = Candidate("B", "dB", "s2", 0.6, xm, 0.6, 10, price_b, True, frozenset({"fastapi"}))
    return Problem((a, b), {"s1": 1, "s2": 1}, 30, budget, Weights(0.35, 0.25, 0.2, 0.2))


# ------------------------------------------------------------------------------ risks


def test_budget_tight_switches_on_just_above_95_percent() -> None:
    """Σ price 950,000 of C 1,000,000 is exactly 95 % → no chip; 950,001 → BUDGET_TIGHT."""
    assert Risk.BUDGET_TIGHT not in team_risks(_two(450_000, 500_000), (0, 1))
    assert Risk.BUDGET_TIGHT in team_risks(_two(450_001, 500_000), (0, 1))


def test_schedule_tight_switches_on_just_above_90_percent() -> None:
    """max t = 27 of T^d 30 is exactly 90 % → no chip; 28 days → SCHEDULE_TIGHT."""
    assert Risk.SCHEDULE_TIGHT not in team_risks(_two(days=27), (0, 1))
    assert Risk.SCHEDULE_TIGHT in team_risks(_two(days=28), (0, 1))


def test_low_teamwork_switches_on_below_half() -> None:
    assert Risk.LOW_TEAMWORK not in team_risks(_two(xm=0.5), (0, 1))
    assert Risk.LOW_TEAMWORK in team_risks(_two(xm=0.499), (0, 1))


def test_single_point_skill_and_newcomer_on_critical_path() -> None:
    """React is needed by a critical milestone and only A holds it; B (a newcomer) holds the
    critical FastAPI skill."""
    risks = team_risks(_two(), (0, 1), critical_skills=frozenset({"react", "fastapi"}))
    assert Risk.SINGLE_POINT_SKILL in risks
    assert Risk.NEWCOMER_ON_CRITICAL_PATH in risks
    assert team_risks(_two(), (0, 1)) == ()
    assert team_risks(_two(), ()) == ()


# ------------------------------------------------------------------- why this team


def test_why_this_team_numbers() -> None:
    p = _two()
    w = why_this_team(p, (0, 1))
    assert w.slots == {"s1": ("A",), "s2": ("B",)}
    assert w.budget_share == pytest.approx(0.9)
    assert w.schedule_share == pytest.approx(20 / 30)
    assert w.summary.newcomers == 1
    assert sum(c.total for c in w.contributions) == pytest.approx(w.summary.fitness)
    assert w.runner_up is None
    assert w.deciding_term is None


def test_runner_up_difference_names_the_deciding_term() -> None:
    """Exact top 2 on a random instance: the deciding term is the one where the recommended team
    gains most over the runner-up, and the term differences add up to the fitness gap."""
    p = random_instance(41, candidates=12, slots=3, min_newcomers=0)
    r = solve_exact(p)
    (best, f1), (second, f2) = r.top[0], r.top[1]
    w = why_this_team(p, best, runner_up=second)
    assert sum(w.runner_up_difference.values()) == pytest.approx(f1 - f2)
    assert w.deciding_term == max(w.runner_up_difference, key=w.runner_up_difference.__getitem__)


def test_compare_teams_is_distinct_best_first_and_skips_infeasible() -> None:
    p = random_instance(42, candidates=12, slots=3, min_newcomers=0)
    r = solve_exact(p)
    rows = compare_teams(p, [*r.top, r.top[0], ((0,), -math.inf)])
    assert [row.team for row in rows] == [t for t, _ in r.top]
    assert all(row.covers_required for row in rows)
    first = summarise(p, r.best)
    assert rows[0].price_paisa == first.price_paisa


# ------------------------------------------------------------------ why not selected


def _lost_bid(seed: int) -> tuple[Problem, tuple[int, ...], float, int]:
    p = random_instance(seed, candidates=12, slots=3, min_newcomers=0)
    best, f = exact(p)
    loser = next(i for i in range(p.size) if i not in best)
    return p, best, f, loser


def test_why_not_selected_gap_and_main_gap() -> None:
    p, best, f, loser = _lost_bid(51)
    w = why_not_selected(p, loser, best, f, exact)
    assert loser in w.forced_team
    assert w.gap == pytest.approx(f - w.forced_fitness)
    assert w.gap >= 0
    term, rival = main_gap(p, loser, best)
    assert (w.main_gap, w.compared_with) == (term, rival)
    if term is not None and rival is not None:
        mine, theirs = p.terms(loser), p.terms(rival)
        gaps = {k: getattr(theirs, k) - getattr(mine, k) for k in ("comp", "team", "time", "cost")}
        assert gaps[term] == max(gaps.values())


def test_why_not_selected_refuses_a_selected_bid() -> None:
    p, best, f, _ = _lost_bid(52)
    with pytest.raises(ValueError, match="recommended team"):
        why_not_selected(p, best[0], best, f, exact)


@settings(max_examples=25, deadline=None)
@given(st.integers(0, 10_000))
def test_counterfactual_price_really_selects_the_bid(seed: int) -> None:
    """§9.8 property: set the bid's price to the reported counterfactual and re-run without any
    lock — the bid is in the best team. The price is a multiple of ৳100 below the bid."""
    p, _best, f, loser = _lost_bid(seed)
    price = price_counterfactual(p, loser, f, exact)
    if price is None:
        return
    assert price % 10_000 == 0
    assert 0 < price <= p.candidates[loser].price_paisa
    cands = list(p.candidates)
    cands[loser] = replace(cands[loser], price_paisa=price)
    rerun, _ = exact(replace(p, candidates=tuple(cands)))
    assert loser in rerun


def test_no_counterfactual_when_half_price_is_not_enough() -> None:
    """A bid far worse on every other term can't win even at half its price."""
    p, _best, f, loser = _lost_bid(53)
    hopeless = replace(p.candidates[loser], competency=0.0, teamwork=0.0, days=30)
    cands = list(p.candidates)
    cands[loser] = hopeless
    q = replace(p, candidates=tuple(cands))
    assert price_counterfactual(q, loser, f, exact) is None
