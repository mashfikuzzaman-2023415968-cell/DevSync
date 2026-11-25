"""Team repair (spec §9.9; D128, D129, D138): remaining members stay locked, the budget after the
fee is respected, candidates are ranked by fitness (top 3), the newcomer minimum is kept or relaxed
with a note, each no-candidate reason, and the project impact on a hand-computed CPM case."""

from __future__ import annotations

import pytest

from app.algorithms.exact_solver import solve_exact
from app.algorithms.fitness import Candidate, Problem, Weights, fitness
from app.algorithms.repair import (
    NEWCOMER_MINIMUM_RELAXED,
    NO_BIDS_FOR_SLOT,
    NONE_AVAILABLE,
    REMAINING_BUDGET_TOO_LOW,
    PlanMilestone,
    affected_milestones,
    rank_replacements,
    repair_impact,
)

pytestmark = pytest.mark.unit
W = Weights(0.35, 0.25, 0.2, 0.2)


def cand(
    bid: str, slot: str, c: float, days: int, price: int, *, newcomer: bool = False
) -> Candidate:
    return Candidate(bid, f"d{bid}", slot, c, 0.6, 0.6, days, price, newcomer, frozenset({slot}))


A = cand("A", "s1", 0.8, 15, 300_000)
B = cand("B", "s2", 0.7, 12, 250_000)
D = cand("D", "s3", 0.9, 10, 300_000)  # best
E = cand("E", "s3", 0.5, 20, 150_000)  # cheap and slow
F = cand("F", "s3", 0.6, 18, 260_000)
N = cand("N", "s3", 0.4, 22, 120_000, newcomer=True)
SLOTS = {"s1": 1, "s2": 1, "s3": 1}


def solver(p: Problem) -> tuple[tuple[int, ...], float]:
    r = solve_exact(p)
    return r.best, r.fitness


def problem(cands: tuple[Candidate, ...], budget: int = 1_000_000, k: int = 0) -> Problem:
    return Problem(cands, SLOTS, 30, budget, W, min_newcomers=k,
                   required_skills=frozenset(SLOTS))  # fmt: skip


def test_remaining_stay_locked_and_candidates_rank_by_fitness() -> None:
    p = problem((A, B, D, E, F))
    r = rank_replacements(p, frozenset({0, 1}), [2, 3, 4], solver)
    assert [c.index for c in r.candidates] == sorted(
        [2, 3, 4], key=lambda i: -fitness(p, {0, 1, i})
    )
    assert r.candidates[0].index == 2  # D is best
    for c in r.candidates:
        assert {0, 1} <= set(c.team)  # the remaining members are kept
        assert c.fitness == pytest.approx(fitness(p, c.team))
    assert r.reasons == ()


def test_only_the_top_three_are_returned_and_the_prefilter_holds() -> None:
    p = problem((A, B, D, E, F, N))
    r = rank_replacements(p, frozenset({0, 1}), [2, 3, 4, 5], solver)
    assert len(r.candidates) == 3
    one = rank_replacements(p, frozenset({0, 1}), [2, 3, 4, 5], solver, prefilter=1)
    assert [c.index for c in one.candidates] == [2]  # D has the best own score


def test_budget_after_fee_is_respected_with_the_shortfall() -> None:
    """A + B = ৳5,500; D would need ৳8,500 of a ৳7,000 budget → 150,000 paisa short; E fits."""
    p = problem((A, B, D, E), budget=700_000)
    r = rank_replacements(p, frozenset({0, 1}), [2, 3], solver)
    assert [c.index for c in r.candidates] == [3]
    assert all(c.price_paisa <= 700_000 for c in r.candidates)
    none = rank_replacements(p, frozenset({0, 1}), [2], solver)
    assert none.candidates == ()
    assert none.reasons == (REMAINING_BUDGET_TOO_LOW,)
    assert none.shortfall_paisa == 150_000


def test_no_bids_and_none_available() -> None:
    p = problem((A, B, D))
    assert rank_replacements(p, frozenset({0, 1}), [], solver).reasons == (NO_BIDS_FOR_SLOT,)
    gone = rank_replacements(p, frozenset({0, 1}), [], solver, unavailable=2)
    assert gone.reasons == (NONE_AVAILABLE,)
    p_low = problem((A, B, D), budget=600_000)
    both = rank_replacements(p_low, frozenset({0, 1}), [2], solver, unavailable=1)
    assert both.reasons == (REMAINING_BUDGET_TOO_LOW, NONE_AVAILABLE)


def test_newcomer_minimum_kept_when_a_newcomer_candidate_exists() -> None:
    p = problem((A, B, D, E, N), k=1)
    r = rank_replacements(p, frozenset({0, 1}), [2, 3, 4], solver)
    assert [c.index for c in r.candidates] == [4]  # only the newcomer satisfies k = 1
    assert r.notes == ()
    assert r.min_newcomers == 1


def test_newcomer_minimum_relaxed_with_a_note_otherwise() -> None:
    p = problem((A, B, D, E), k=1)
    r = rank_replacements(p, frozenset({0, 1}), [2, 3], solver)
    assert r.notes == (NEWCOMER_MINIMUM_RELAXED,)
    assert r.min_newcomers == 0
    assert r.candidates[0].index == 2


PLAN = [  # §18.2 "Online ordering system": duration 24, Frontend has 4 days of slack
    PlanMilestone("req", "Requirements & design", 4, (), frozenset({"uiux"})),
    PlanMilestone("db", "Database", 5, ("req",), frozenset({"postgres"})),
    PlanMilestone("api", "Backend API", 8, ("db",), frozenset({"fastapi"})),
    PlanMilestone("fe", "Frontend", 9, ("req",), frozenset({"react"})),
    PlanMilestone("int", "Integration", 3, ("api", "fe"), frozenset({"react", "fastapi"})),
    PlanMilestone("qa", "Testing & launch", 4, ("int",), frozenset({"testing"})),
]


def test_impact_against_a_hand_computed_cpm() -> None:
    """React leaves (20 days), the candidate needs 30: ×1.5. Frontend 9 → 14 (13.5 up), Integration
    3 → 5 (4.5 up). Critical paths: req 4 → db 5 → api 8 → int 5 → qa 4 = 26, and req 4 → fe 14 →
    int 5 → qa 4 = 27. New duration 27, delay +3 over the baseline 24."""
    imp = repair_impact(PLAN, "react", started=False, departed_days=20, candidate_days=30,
                        baseline_days=24, team_price_paisa=9_900_000,
                        budget_after_fee_paisa=10_800_000)  # fmt: skip
    assert imp.affected == ("fe", "int")
    assert (imp.new_days, imp.delay_days) == (27, 3)
    assert imp.budget_delta_paisa == -900_000  # ৳9,000 under the budget after fee
    assert not imp.budget_only


def test_a_faster_candidate_can_shorten_the_plan_only_off_the_critical_path() -> None:
    imp = repair_impact(PLAN, "fastapi", started=False, departed_days=20, candidate_days=10,
                        baseline_days=24, team_price_paisa=1, budget_after_fee_paisa=1)  # fmt: skip
    # Backend API 8 → 4, Integration 3 → 2: req 4 → fe 9 → int 2 → qa 4 = 19 is now critical.
    assert imp.new_days == 19
    assert imp.delay_days == -5


def test_after_start_done_milestones_are_not_affected() -> None:
    plan = [replace_done(m) if m.id in {"fe", "int"} else m for m in PLAN]
    assert affected_milestones(plan, "react", started=True) == ()
    assert affected_milestones(plan, "react", started=False) == ("fe", "int")
    imp = repair_impact(
        plan, "react", started=True, departed_days=20, candidate_days=40,
        baseline_days=24, team_price_paisa=5, budget_after_fee_paisa=10,
    )  # fmt: skip
    assert imp.budget_only
    assert imp.delay_days == 0


def test_impact_refuses_nonsense_days() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        repair_impact(PLAN, "react", started=False, departed_days=0, candidate_days=5,
                      baseline_days=24, team_price_paisa=1, budget_after_fee_paisa=1)  # fmt: skip


def replace_done(m: PlanMilestone) -> PlanMilestone:
    return PlanMilestone(m.id, m.name, m.duration_days, m.predecessors, m.skills, done=True)
