"""Role assessment scoring (role assessment spec §5.3, §16 cases 27–33, §17.1–17.2).

`tests/fixtures/assessment_scoring_vectors.json` holds the shared cases: these tests check the
Python reference against them, and `tests/integration/test_role_assessment_db.py` checks the SQL
scoring against the same file (parity).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.algorithms.assessment_scoring import (
    AnsweredQuestion,
    ScoredCompetency,
    evidence_score,
    score_attempt,
)

pytestmark = pytest.mark.unit

VECTORS = Path(__file__).resolve().parents[1] / "fixtures" / "assessment_scoring_vectors.json"
RULE = {"pass_overall_bp": 6000, "floor_bp": 4000, "heavy_weight_bp": 2000}


def _vectors() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(VECTORS.read_text(encoding="utf-8"))["vectors"]
    return data


def _score(v: dict[str, Any]) -> Any:
    comps = [
        ScoredCompetency(c["id"], c["code"], c["code"], c["weight_bp"]) for c in v["competencies"]
    ]
    answers = [
        AnsweredQuestion(q["competency"], q["difficulty"], q["correct"]) for q in v["questions"]
    ]
    return score_attempt(comps, answers, ended_early=v.get("ended_early", False), **v["rule"])


def test_there_are_at_least_thirty_shared_vectors() -> None:
    assert len(_vectors()) >= 30


@pytest.mark.parametrize("vector", _vectors(), ids=lambda v: v["name"])
def test_python_reference_matches_every_vector(vector: dict[str, Any]) -> None:
    result = _score(vector)
    expect = vector["expect"]
    assert result.overall_bp == expect["overall_bp"]
    assert result.passed is expect["passed"]
    assert str(result.score) == expect["score"]
    assert [c.score_bp for c in result.breakdown] == expect["score_bp"]


def _one(
    weight: int, *answers: tuple[int, bool]
) -> tuple[list[ScoredCompetency], list[AnsweredQuestion]]:
    return (
        [ScoredCompetency("c", "c", "c", weight)],
        [AnsweredQuestion("c", d, ok) for d, ok in answers],
    )


def test_difficulty_weights_are_two_three_and_four() -> None:
    comps, answers = _one(10_000, (1, True), (2, False), (3, True))
    result = score_attempt(comps, answers, **RULE)
    assert result.breakdown[0].earned_w == 6
    assert result.breakdown[0].possible_w == 9
    assert result.breakdown[0].score_bp == 6666  # floor(10000 × 6 / 9)


def test_exactly_sixty_overall_and_forty_on_a_heavy_competency_passes() -> None:
    # §16 case 28 (inclusive).
    comps = [ScoredCompetency("a", "a", "a", 5000), ScoredCompetency("b", "b", "b", 5000)]
    answers = [AnsweredQuestion("a", 1, True), AnsweredQuestion("a", 1, True),
               AnsweredQuestion("a", 1, True), AnsweredQuestion("a", 1, True),
               AnsweredQuestion("a", 1, True),
               AnsweredQuestion("b", 1, True), AnsweredQuestion("b", 1, True),
               AnsweredQuestion("b", 1, False), AnsweredQuestion("b", 1, False),
               AnsweredQuestion("b", 1, False)]  # fmt: skip
    result = score_attempt(comps, answers, **RULE)
    assert [c.score_bp for c in result.breakdown] == [10_000, 4000]
    assert result.overall_bp == 7000
    assert result.passed


def test_one_basis_point_below_the_pass_mark_fails() -> None:
    # §16 case 29: the threshold compares basis points exactly.
    result = score_attempt(
        [ScoredCompetency("a", "a", "a", 10_000)], [], pass_overall_bp=6000, floor_bp=0,
        heavy_weight_bp=2000,
    )  # fmt: skip
    assert result.overall_bp == 0
    assert not result.passed


def test_a_heavy_competency_under_the_floor_fails_despite_a_high_score() -> None:
    # §16 case 30: weight exactly 20 % is heavy.
    comps = [ScoredCompetency("a", "a", "a", 8000), ScoredCompetency("b", "b", "b", 2000)]
    answers = [AnsweredQuestion("a", 2, True)] * 4 + [
        AnsweredQuestion("b", 2, True), AnsweredQuestion("b", 2, False),
        AnsweredQuestion("b", 2, False),
    ]  # fmt: skip
    result = score_attempt(comps, answers, **RULE)
    assert result.overall_bp >= 6000
    assert result.breakdown[1].score_bp == 3333
    assert not result.passed


def test_a_light_competency_at_zero_can_still_pass() -> None:
    # §16 case 31: weight 15 % is below the heavy weight.
    comps = [ScoredCompetency("a", "a", "a", 8500), ScoredCompetency("b", "b", "b", 1500)]
    answers = [AnsweredQuestion("a", 2, True)] * 3 + [AnsweredQuestion("b", 2, False)]
    result = score_attempt(comps, answers, **RULE)
    assert result.breakdown[1].score_bp == 0
    assert result.passed


def test_an_attempt_that_ended_early_never_passes() -> None:
    # §16 case 32.
    comps, answers = _one(10_000, (2, True), (2, True))
    assert score_attempt(comps, answers, **RULE).passed
    assert not score_attempt(comps, answers, ended_early=True, **RULE).passed


def test_skipping_everything_scores_zero() -> None:
    # §16 case 27.
    comps, answers = _one(10_000, (1, False), (2, False), (3, False))
    result = score_attempt(comps, answers, **RULE)
    assert result.overall_bp == 0
    assert result.score == Decimal("0.000")
    assert not result.passed


def test_evidence_score_rounds_down_to_three_decimals() -> None:
    assert evidence_score(7999) == Decimal("0.799")
    assert evidence_score(10_000) == Decimal("1.000")
    assert evidence_score(0) == Decimal("0.000")


def test_strongest_and_weakest_break_ties_by_weight_then_code() -> None:
    comps = [ScoredCompetency("a", "a", "A", 4000), ScoredCompetency("b", "b", "B", 6000)]
    answers = [AnsweredQuestion("a", 1, True), AnsweredQuestion("b", 1, True)]
    result = score_attempt(comps, answers, **RULE)
    assert result.strongest.code == "b"  # equal scores: the heavier one
    assert result.weakest.code == "b"


@settings(max_examples=200, deadline=None)
@given(
    st.lists(st.tuples(st.integers(1, 3), st.booleans()), min_size=1, max_size=20),
    st.integers(0, 19),
)
def test_one_more_correct_answer_never_lowers_the_score(
    answers: list[tuple[int, bool]], flip: int
) -> None:
    """Monotonicity (§17.2)."""
    comps = [ScoredCompetency("a", "a", "a", 6000), ScoredCompetency("b", "b", "b", 4000)]
    qs = [AnsweredQuestion("a" if i % 2 else "b", d, ok) for i, (d, ok) in enumerate(answers)]
    i = flip % len(qs)
    better = [*qs[:i], AnsweredQuestion(qs[i].competency_id, qs[i].difficulty, True), *qs[i + 1 :]]
    assert (
        score_attempt(comps, better, **RULE).overall_bp
        >= score_attempt(comps, qs, **RULE).overall_bp
    )
