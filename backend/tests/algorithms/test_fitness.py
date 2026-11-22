"""Fitness ([PCS] Eq. 17–19) and feasibility (spec §9.3) by hand. Test names carry the equation
ids for docs/PAPER_ALIGNMENT.md (eq17, eq18, eq19) and the ambiguity ids A3, A7, A10 (D91).

Fixture: T^d = 30 days, C (budget after fee) = 1,000,000 paisa, weights C1–C4 = 0.4/0.3/0.2/0.1.
    A  slot s1  C 0.8  X_m 0.6  t 15  c 300,000   t̄ = 0.5  c̄ = 0.3
       term = 0.4·0.8 + 0.3·0.6 − 0.2·0.5 − 0.1·0.3 = 0.32 + 0.18 − 0.10 − 0.03 = 0.37
    B  slot s2  C 0.5  X_m 0.9  t 30  c 500,000   t̄ = 1.0  c̄ = 0.5
       term = 0.20 + 0.27 − 0.20 − 0.05 = 0.22
    D  slot s3  C 0.7  X_m 0.4  t 6   c 100,000   t̄ = 0.2  c̄ = 0.1
       term = 0.28 + 0.12 − 0.04 − 0.01 = 0.35
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from app.algorithms.filtering import Mode
from app.algorithms.fitness import (
    Candidate,
    Infeasible,
    Problem,
    Weights,
    breakdown,
    fitness,
    infeasibility,
    member_terms,
)

pytestmark = pytest.mark.unit

W = Weights(0.4, 0.3, 0.2, 0.1)
A = Candidate("A", "dA", "s1", 0.8, 0.6, 0.7, 15, 300_000, False, frozenset({"react"}))
B = Candidate("B", "dB", "s2", 0.5, 0.9, 0.6, 30, 500_000, True, frozenset({"fastapi"}))
D = Candidate("D", "dD", "s3", 0.7, 0.4, 0.5, 6, 100_000, False, frozenset({"pg"}))
E = Candidate("E", "dE", "s1", 0.6, 0.6, 0.6, 10, 200_000, True, frozenset({"react"}))


def two(**kw: object) -> Problem:
    return Problem((A, B), {"s1": 1, "s2": 1}, 30, 1_000_000, W, **kw)  # type: ignore[arg-type]


def three(**kw: object) -> Problem:
    return Problem((A, B, D), {"s1": 1, "s2": 1, "s3": 1}, 30, 1_000_000, W, **kw)  # type: ignore[arg-type]


def test_eq17_two_member_team_by_hand() -> None:
    """F = 0.37 + 0.22 = 0.59."""
    assert fitness(two(), {0, 1}) == pytest.approx(0.59)


def test_eq17_three_member_team_and_breakdown() -> None:
    """F = 0.37 + 0.22 + 0.35 = 0.94; the breakdown lists each member's terms."""
    p = three()
    assert fitness(p, {0, 1, 2}) == pytest.approx(0.94)
    rows = {b.bid_id: b for b in breakdown(p, [0, 1, 2])}
    assert rows["A"].comp == pytest.approx(0.32)
    assert rows["A"].team == pytest.approx(0.18)
    assert rows["A"].time == pytest.approx(-0.10)
    assert rows["A"].cost == pytest.approx(-0.03)
    assert rows["D"].total == pytest.approx(0.35)


def test_eq18_cost_is_normalised_by_the_budget_after_fee() -> None:
    """c̄ = c/C: 300,000 / 1,000,000 = 0.3 → −C4·c̄ = −0.03."""
    assert member_terms(two(), 0).cost == pytest.approx(-0.03)


def test_eq19_time_is_normalised_by_the_deadline() -> None:
    """t̄ = t/T^d: 30/30 = 1 → −C3·t̄ = −0.2 for B."""
    assert member_terms(two(), 1).time == pytest.approx(-0.2)


def test_weights_are_normalised_to_sum_one() -> None:
    """Sliders 4/3/2/1 give the same fitness as 0.4/0.3/0.2/0.1."""
    p = replace(two(), weights=Weights(4, 3, 2, 1))
    assert fitness(p, {0, 1}) == pytest.approx(0.59)


@pytest.mark.parametrize("w", [(0, 0, 0, 0), (-1, 1, 1, 1), (math.inf, 1, 1, 1)])
def test_invalid_weights_are_refused(w: tuple[float, float, float, float]) -> None:
    with pytest.raises(ValueError, match="weight"):
        Weights(*w).normalised()


def test_A3_infeasible_fitness() -> None:  # noqa: N802 — name required by spec §9.0
    """A3 (D111): an infeasible team scores −∞, never chosen. The paper prints −1, but a feasible
    fitness can be below −1: with all weight on time and t̄ = 1 for both members F = −2, which a
    −1 for infeasible teams would rank *above* a real team."""
    assert fitness(two(), {0}) == -math.inf
    time_only = replace(two(), weights=Weights(0, 0, 1, 0))
    slow = (replace(A, days=30), replace(B, days=30))
    assert fitness(replace(time_only, candidates=slow), {0, 1}) == pytest.approx(-2.0)


def test_A7_performance_term_only_behind_its_setting() -> None:  # noqa: N802 — spec §9.0
    """A7: off by default (P has no weight). With `include_performance`, C5 = C1 and the five
    weights 0.4/0.3/0.2/0.1/0.4 are normalised by 1.4: A's term becomes
    (0.32 + 0.18 − 0.10 − 0.03 + 0.4·0.7) / 1.4 = 0.65 / 1.4."""
    assert member_terms(two(), 0).perf == 0
    with_p = member_terms(two(include_performance=True), 0)
    assert with_p.total == pytest.approx(0.65 / 1.4)


def test_A10_cost_normaliser_is_the_budget_after_fee() -> None:  # noqa: N802 — spec §9.0
    """A10: C in Eq. 18 is the budget after the platform fee (the service passes it): the same
    price weighs more against a smaller after-fee budget."""
    small = replace(two(), budget_after_fee_paisa=600_000)
    assert member_terms(small, 0).cost == pytest.approx(-0.1 * 300_000 / 600_000)


# ------------------------------------------------------------------ feasibility, one rule each


def test_feasible_team() -> None:
    assert infeasibility(three(), {0, 1, 2}) is None


def test_rule_team_size() -> None:
    assert infeasibility(three(), {0, 1}) is Infeasible.SIZE


def test_rule_slot_counts() -> None:
    """Two members in s1 and none in s2: right size, wrong slots."""
    p = Problem((A, E, B), {"s1": 1, "s2": 1}, 30, 1_000_000, W)
    assert infeasibility(p, {0, 1}) is Infeasible.SLOT_COUNT


def test_rule_distinct_developers() -> None:
    twin = replace(B, bid_id="B2", developer_id="dA")
    p = Problem((A, twin), {"s1": 1, "s2": 1}, 30, 1_000_000, W)
    assert infeasibility(p, {0, 1}) is Infeasible.DUPLICATE_DEVELOPER


def test_rule_budget_after_fee() -> None:
    """300,000 + 500,000 = 800,000 > 700,000."""
    assert infeasibility(replace(two(), budget_after_fee_paisa=700_000), {0, 1}) is (
        Infeasible.OVER_BUDGET
    )
    assert infeasibility(replace(two(), budget_after_fee_paisa=800_000), {0, 1}) is None


def test_rule_skill_coverage() -> None:
    p = two(required_skills=frozenset({"react", "fastapi", "figma"}))
    assert infeasibility(p, {0, 1}) is Infeasible.SKILL_COVERAGE


def test_rule_newcomer_minimum() -> None:
    """B is a newcomer: k = 1 holds, k = 2 doesn't."""
    assert infeasibility(two(min_newcomers=1), {0, 1}) is None
    assert infeasibility(two(min_newcomers=2), {0, 1}) is Infeasible.NEWCOMERS


def test_replication_checks_only_eq13() -> None:
    """pcs_replication (D114): only the size and distinct developers; slots, budget, coverage and
    the newcomer minimum are DevSync extensions."""
    p = Problem((A, E, B), {"s1": 1, "s2": 1}, 30, 100, W, min_newcomers=3,
                required_skills=frozenset({"figma"}), mode=Mode.PCS_REPLICATION)  # fmt: skip
    assert infeasibility(p, {0, 1}) is None
    assert infeasibility(p, {0}) is Infeasible.SIZE


@pytest.mark.parametrize(
    "kw",
    [
        {"deadline_days": 0},
        {"budget_after_fee_paisa": 0},
        {"slots": {}},
        {"slots": {"s1": 0, "s2": 1}},
        {"min_newcomers": -1},
        {"locked": frozenset({5})},
    ],
)
def test_invalid_problems_are_refused(kw: dict[str, object]) -> None:
    base = {"candidates": (A, B), "slots": {"s1": 1, "s2": 1}, "deadline_days": 30,
            "budget_after_fee_paisa": 1_000_000, "weights": W}  # fmt: skip
    with pytest.raises(ValueError):  # noqa: PT011 - each case has its own message
        Problem(**{**base, **kw})  # type: ignore[arg-type]


def test_candidate_in_unknown_slot_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown slot"):
        Problem((replace(A, slot_id="nope"),), {"s1": 1}, 30, 1_000_000, W)
