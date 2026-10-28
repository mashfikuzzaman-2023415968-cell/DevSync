"""Question selection and order for a role attempt (role assessment spec §5.2, §17.1–17.2)."""

from __future__ import annotations

from collections import Counter

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.algorithms import role_blueprint as rb
from app.algorithms.assessment_selection import (
    Allocation,
    PoolQuestion,
    SelectionUnavailable,
    order_questions,
    select_questions,
)

pytestmark = pytest.mark.unit

ALLOC = [
    Allocation("A", "auth", 4000, 1, 2, 2),
    Allocation("B", "api", 3000, 1, 2, 1),
    Allocation("C", "db", 2000, 1, 1, 0),
    Allocation("D", "err", 1000, 1, 0, 0),
]


def _pool(per: int = 6) -> list[PoolQuestion]:
    return [
        PoolQuestion(f"{c}-{d}-{i}", c, d, i) for c in "ABCD" for d in (1, 2, 3) for i in range(per)
    ]


def _difficulty(qid: str) -> int:
    return int(qid.split("-")[1])


def test_the_allocation_is_respected_exactly() -> None:
    sel = select_questions(ALLOC, _pool(), frozenset(), 7)
    got = Counter((q.split("-")[0], _difficulty(q)) for q in sel.question_ids)
    want = Counter({(a.competency_id, d): a.of(d) for a in ALLOC for d in (1, 2, 3) if a.of(d)})
    assert got == want
    assert len(sel.question_ids) == 12


def test_no_question_twice() -> None:
    sel = select_questions(ALLOC, _pool(per=2), frozenset(), 3)
    assert len(set(sel.question_ids)) == len(sel.question_ids)


def test_recently_seen_questions_are_avoided_while_others_remain() -> None:
    pool = _pool()
    seen = frozenset(q.question_id for q in pool if q.question_id.endswith("-0"))
    sel = select_questions(ALLOC, pool, seen, 11)
    assert not (set(sel.question_ids) & seen)
    assert not sel.reused_seen


def test_seen_questions_are_reused_only_when_nothing_else_is_left() -> None:
    pool = _pool(per=1)
    seen = frozenset(q.question_id for q in pool)
    sel = select_questions([Allocation("C", "db", 10_000, 1, 1, 0)], pool, seen, 1)
    assert sel.reused_seen
    assert len(sel.question_ids) == 2


def test_least_served_questions_are_preferred() -> None:
    pool = [PoolQuestion(f"A-2-{i}", "A", 2, i * 10) for i in range(20)]
    picks = {
        select_questions(
            [Allocation("A", "a", 10_000, 0, 1, 0)], pool, frozenset(), seed
        ).question_ids[0]
        for seed in range(50)
    }
    assert picks <= {f"A-2-{i}" for i in range(5)}  # randomesque among the 5 least served
    assert len(picks) > 1


def test_selection_is_deterministic_per_seed() -> None:
    a = select_questions(ALLOC, _pool(), frozenset(), 99)
    b = select_questions(ALLOC, _pool(), frozenset(), 99)
    assert a == b


def test_too_small_a_pool_is_unavailable() -> None:
    pool = [q for q in _pool() if not (q.competency_id == "A" and q.difficulty == 3)]
    with pytest.raises(SelectionUnavailable):
        select_questions(ALLOC, pool, frozenset(), 1)


def test_order_opens_with_a_medium_question_and_alternates_competencies() -> None:
    sel = select_questions(ALLOC, _pool(), frozenset(), 5)
    first = sel.question_ids[0]
    assert _difficulty(first) == 2
    assert first.startswith("A")  # the heaviest competency
    comps = [q.split("-")[0] for q in sel.question_ids]
    assert comps[0] != comps[1]


def test_order_follows_the_medium_easy_hard_pattern() -> None:
    picked = {("A", 2): ["m1"], ("B", 1): ["e1"], ("A", 3): ["h1"], ("B", 2): ["m2"]}
    alloc = [Allocation("A", "a", 6000, 0, 1, 1), Allocation("B", "b", 4000, 1, 1, 0)]
    assert order_questions(alloc, picked) == ("m1", "e1", "h1", "m2")


@settings(max_examples=150, deadline=None)
@given(
    st.lists(st.integers(0, 6), min_size=3, max_size=6),
    st.text(alphabet="abcdefghij login roles sql schema component", max_size=120),
    st.integers(0, 10_000),
)
def test_blueprint_invariants_hold_for_any_bank_and_text(
    stock: list[int], text: str, seed: int
) -> None:
    """Weights sum to 10,000 in [1,000, 4,000] steps of 500; allocation sums to the count; the
    selection serves exactly the allocation; the same input gives the same output (§17.2)."""
    skill = "s"
    catalogue = {
        skill: [
            rb.Competency(f"c{i}", skill, f"comp_{i}", f"Comp {i}", i < 3, ("login", "sql"), i)
            for i in range(len(stock))
        ]
    }
    counts = {(f"c{i}", d): stock[i] for i in range(len(stock)) for d in (1, 2, 3)}
    inp = rb.BlueprintInput(skill, {skill: "Skill"}, [frozenset({skill})], text, catalogue, counts)
    result = rb.build_blueprint(inp)
    assert result == rb.build_blueprint(inp)
    if isinstance(result, rb.Unavailable):
        return
    weights = [c.weight_bp for c in result.competencies]
    assert sum(weights) == 10_000
    assert all(1000 <= w <= 4000 and w % 500 == 0 for w in weights)
    assert sum(c.question_count for c in result.competencies) == result.question_count
    pool = [
        PoolQuestion(f"{c.competency_id}-{d}-{i}", c.competency_id, d, 0)
        for c in result.competencies
        for d in (1, 2, 3)
        for i in range(counts[(c.competency_id, d)])
    ]
    alloc = [
        Allocation(c.competency_id, c.code, c.weight_bp, c.easy, c.medium, c.hard)
        for c in result.competencies
    ]
    sel = select_questions(alloc, pool, frozenset(), seed)
    assert len(sel.question_ids) == result.question_count
    assert len(set(sel.question_ids)) == result.question_count
