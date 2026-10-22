"""Property tests for Algorithm 1 filtering (spec §9.2, §16 "invariants"). Pure, no I/O.

Random bid sets over two slots check the invariants that make the filter defensible:
deterministic, monotone in the thresholds, never hurt by extra bids, shortlist bounded by K_s,
the explanation trace agrees with the verdict, and the team-cost estimate is the true minimum.
"""

from __future__ import annotations

import itertools

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.algorithms.filtering import (
    Advancement,
    BidInput,
    FilterParams,
    Mode,
    ProjectInput,
    ReasonCode,
    SlotSpec,
    cheapest_team_cost,
    classify_bid,
    explain_bid,
    filter_bids,
)

pytestmark = [pytest.mark.property, pytest.mark.unit]

PROJECT = ProjectInput(
    deadline_days=30,
    budget_after_fee_paisa=11_400_000,
    slots={"s1": SlotSpec("react", 2), "s2": SlotSpec("api", 1)},
)

# The check that fails first in `explain_bid` maps to `classify_bid`'s reason.
CHECK_REASON = {
    "account_active": ReasonCode.SUSPENDED,
    "has_slot_skill": ReasonCode.SKILL_MISMATCH,
    "no_conflict": ReasonCode.SELF_DEALING,
    "available": ReasonCode.UNAVAILABLE,
    "skill_evidence": ReasonCode.NO_SKILL_EVIDENCE,
    "performance": ReasonCode.LOW_PERFORMANCE,
    "competency": ReasonCode.LOW_COMPETENCY,
    "days": ReasonCode.TOO_SLOW,
    "price": ReasonCode.OVER_BUDGET,
}

scores = st.floats(0, 1, allow_nan=False)


@st.composite
def bid_inputs(draw: st.DrawFn, index: int) -> BidInput:
    slot = draw(st.sampled_from(["s1", "s2"]))
    return BidInput(
        bid_id=f"b{index}",
        slot_id=slot,
        skill_id="react" if slot == "s1" else "api",
        developer_id=f"d{index}",
        is_newcomer=draw(st.booleans()),
        p=draw(scores),
        c=draw(scores),
        t_days=draw(st.integers(1, 60)),
        c_paisa=draw(st.integers(1, 20_000_000)),
        skill_evidence_score=draw(st.none() | scores),
        has_slot_skill=draw(st.booleans()),
        active=draw(st.booleans()),
        available=draw(st.booleans()),
        self_dealing=draw(st.booleans()),
    )


@st.composite
def bid_sets(draw: st.DrawFn, max_size: int = 14) -> list[BidInput]:
    n = draw(st.integers(0, max_size))
    return [draw(bid_inputs(i)) for i in range(n)]


thresholds = st.tuples(
    st.sampled_from([0.30, 0.35, 0.40, 0.45, 0.50]), st.sampled_from([0.25, 0.30, 0.35, 0.40])
)
modes = st.sampled_from([Mode.DEVSYNC, Mode.PCS_REPLICATION])
advancements = st.sampled_from(list(Advancement))


def _params(p0: float, c0: float, mode: Mode, adv: Advancement = Advancement.C) -> FilterParams:
    return FilterParams(p0=p0, c0=c0, team_size=3, mode=mode, advancement=adv)


@given(bids=bid_sets(), th=thresholds, mode=modes, adv=advancements)
@settings(max_examples=150, deadline=None)
def test_deterministic(
    bids: list[BidInput], th: tuple[float, float], mode: Mode, adv: Advancement
) -> None:
    params = _params(*th, mode, adv)
    assert filter_bids(bids, PROJECT, params) == filter_bids(bids, PROJECT, params)
    # Input order does not change the outcome (sets) or the per-slot ordering.
    shuffled = list(reversed(bids))
    a, b = filter_bids(bids, PROJECT, params), filter_bids(shuffled, PROJECT, params)
    assert set(a.eligible) == set(b.eligible)
    assert a.shortlisted == b.shortlisted


@given(bids=bid_sets(), mode=modes)
@settings(max_examples=150, deadline=None)
def test_lower_thresholds_never_reduce_eligibility(bids: list[BidInput], mode: Mode) -> None:
    for (p_hi, c_hi), (p_lo, c_lo) in itertools.pairwise(
        [(0.50, 0.45), (0.45, 0.40), (0.40, 0.35), (0.30, 0.25)]
    ):
        strict = {
            b.bid_id
            for b in bids
            if classify_bid(b, PROJECT, _params(p_hi, c_hi, mode), p_hi, c_hi) is None
        }
        loose = {
            b.bid_id
            for b in bids
            if classify_bid(b, PROJECT, _params(p_lo, c_lo, mode), p_lo, c_lo) is None
        }
        assert strict <= loose


@given(bids=bid_sets(), extra=bid_inputs(99), th=thresholds)
@settings(max_examples=150, deadline=None)
def test_adding_a_bid_never_removes_an_eligible_one(
    bids: list[BidInput], extra: BidInput, th: tuple[float, float]
) -> None:
    # Devsync relaxation only loosens as more bids arrive is NOT guaranteed (a new bid can end
    # relaxation earlier), so the invariant holds at fixed thresholds: eligibility is per bid.
    params = _params(*th, Mode.DEVSYNC)
    before = {b.bid_id for b in bids if classify_bid(b, PROJECT, params, *th) is None}
    after = {b.bid_id for b in [*bids, extra] if classify_bid(b, PROJECT, params, *th) is None}
    assert before <= after


@given(bids=bid_sets(), th=thresholds, mode=modes, adv=advancements)
@settings(max_examples=150, deadline=None)
def test_result_partitions_the_bids(
    bids: list[BidInput], th: tuple[float, float], mode: Mode, adv: Advancement
) -> None:
    result = filter_bids(bids, PROJECT, _params(*th, mode, adv))
    eligible = set(result.eligible)
    rejected = {bid_id for bid_id, _ in result.rejected}
    assert eligible.isdisjoint(rejected)
    assert eligible | rejected == {b.bid_id for b in bids}
    shortlisted = {i for ids in result.shortlisted.values() for i in ids}
    assert shortlisted | set(result.not_shortlisted) == eligible
    assert shortlisted.isdisjoint(result.not_shortlisted)


@given(bids=bid_sets(max_size=30), th=thresholds, adv=advancements)
@settings(max_examples=100, deadline=None)
def test_shortlist_never_exceeds_k(
    bids: list[BidInput], th: tuple[float, float], adv: Advancement
) -> None:
    params = _params(*th, Mode.DEVSYNC, adv)
    result = filter_bids(bids, PROJECT, params)
    for slot_id, spec in PROJECT.slots.items():
        k = max(params.shortlist_factor * spec.count, params.shortlist_min)
        assert len(result.shortlisted[slot_id]) <= k
        assert all(b.slot_id == slot_id for b in bids if b.bid_id in result.shortlisted[slot_id])


@given(bids=bid_sets(), th=thresholds, mode=modes)
@settings(max_examples=150, deadline=None)
def test_relaxation_is_bounded_and_reported_in_steps(
    bids: list[BidInput], th: tuple[float, float], mode: Mode
) -> None:
    params = _params(*th, mode)
    result = filter_bids(bids, PROJECT, params)
    assert len(result.relaxations) <= params.relax_max_steps
    for r in result.relaxations:
        assert r.p0 == max(0.0, round(params.p0 - r.step * params.relax_step, 2))
        assert r.c0 == max(0.0, round(params.c0 - r.step * params.relax_step, 2))
    if mode is Mode.PCS_REPLICATION:
        # The paper re-initializes only an empty candidate set: before every relaxation step,
        # nobody qualified at the previous thresholds.
        previous = [(params.p0, params.c0)] + [(r.p0, r.c0) for r in result.relaxations[:-1]]
        for p0, c0 in previous[: len(result.relaxations)]:
            assert all(classify_bid(b, PROJECT, params, p0, c0) is not None for b in bids)


@given(bids=bid_sets(), th=thresholds, mode=modes)
@settings(max_examples=200, deadline=None)
def test_explanation_agrees_with_the_verdict(
    bids: list[BidInput], th: tuple[float, float], mode: Mode
) -> None:
    params = _params(*th, mode)
    for b in bids:
        reason = classify_bid(b, PROJECT, params, *th)
        checks = explain_bid(b, PROJECT, params, *th)
        failing = [c for c in checks if not c.ok]
        if reason is None:
            assert failing == []
        else:
            assert CHECK_REASON[failing[0].name] is reason


@given(bids=bid_sets(max_size=8), th=thresholds)
@settings(max_examples=100, deadline=None)
def test_team_cost_is_the_true_minimum(bids: list[BidInput], th: tuple[float, float]) -> None:
    result = filter_bids(bids, PROJECT, _params(*th, Mode.DEVSYNC))
    eligible = set(result.eligible)
    cost = cheapest_team_cost(bids, eligible, PROJECT)
    # Brute force: every way to pick `count` eligible bids per slot.
    best: int | None = None
    pools = {
        s: [b.c_paisa for b in bids if b.slot_id == s and b.bid_id in eligible]
        for s in PROJECT.slots
    }
    if all(len(pools[s]) >= spec.count for s, spec in PROJECT.slots.items()):
        for pick1 in itertools.combinations(pools["s1"], PROJECT.slots["s1"].count):
            for pick2 in itertools.combinations(pools["s2"], PROJECT.slots["s2"].count):
                total = sum(pick1) + sum(pick2)
                best = total if best is None else min(best, total)
        assert cost.complete
        assert cost.total_paisa == best
    else:
        assert not cost.complete
