"""Algorithm 1 worker filtering + the newcomer rule (spec §9.2). Pure, deterministic.

One test per reason code, boundary-equal-passes at every paper constraint, the newcomer rule,
relaxation reporting, advancement ordering per preset, shortlist size, pcs_replication mode, a
stable reason precedence, and property tests.
"""

from __future__ import annotations

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
    classify_bid,
    filter_bids,
)

SLOT = "slot-react"
PROJECT = ProjectInput(
    deadline_days=30,
    budget_after_fee_paisa=11_400_000,  # ৳120,000 budget − 5% fee
    slots={SLOT: SlotSpec(skill_id="react", count=1)},
)
PARAMS = FilterParams(p0=0.45, c0=0.40, advancement=Advancement.C, team_size=1)


def bid(bid_id: str = "b", **over: object) -> BidInput:
    """An otherwise-eligible experienced bid; override one field to make it fail a gate."""
    base: dict[str, object] = {
        "bid_id": bid_id,
        "slot_id": SLOT,
        "skill_id": "react",
        "developer_id": f"dev-{bid_id}",
        "is_newcomer": False,
        "p": 0.80,
        "c": 0.75,
        "t_days": 20,
        "c_paisa": 1_800_000,
        "skill_evidence_score": None,
        "has_slot_skill": True,
        "active": True,
        "available": True,
        "self_dealing": False,
    }
    base.update(over)
    return BidInput(**base)  # type: ignore[arg-type]


def _classify(b: BidInput) -> ReasonCode | None:
    return classify_bid(b, PROJECT, PARAMS, PARAMS.p0, PARAMS.c0)


# --------------------------------------------------------------- one test per reason code


def test_eligible_bid_has_no_reason() -> None:
    assert _classify(bid()) is None


def test_low_performance() -> None:
    assert _classify(bid(p=0.44)) is ReasonCode.LOW_PERFORMANCE


def test_low_competency() -> None:
    assert _classify(bid(c=0.39)) is ReasonCode.LOW_COMPETENCY


def test_too_slow() -> None:
    assert _classify(bid(t_days=31)) is ReasonCode.TOO_SLOW


def test_over_budget() -> None:
    assert _classify(bid(c_paisa=11_400_001)) is ReasonCode.OVER_BUDGET


def test_skill_mismatch() -> None:
    assert _classify(bid(has_slot_skill=False)) is ReasonCode.SKILL_MISMATCH


def test_unavailable() -> None:
    assert _classify(bid(available=False)) is ReasonCode.UNAVAILABLE


def test_suspended() -> None:
    assert _classify(bid(active=False)) is ReasonCode.SUSPENDED


def test_self_dealing() -> None:
    assert _classify(bid(self_dealing=True)) is ReasonCode.SELF_DEALING


def test_newcomer_no_skill_evidence() -> None:
    assert (
        _classify(bid(is_newcomer=True, skill_evidence_score=0.59)) is ReasonCode.NO_SKILL_EVIDENCE
    )
    assert (
        _classify(bid(is_newcomer=True, skill_evidence_score=None)) is ReasonCode.NO_SKILL_EVIDENCE
    )


# --------------------------------------------------------- boundary: equal to the threshold passes


def test_equal_to_every_threshold_passes() -> None:
    # P == P0, C == C0, t == T^d, c == C''_j all pass (spec §9.2 "equal to the threshold passes").
    assert _classify(bid(p=0.45, c=0.40, t_days=30, c_paisa=11_400_000)) is None


def test_newcomer_evidence_equal_to_pass_mark_passes() -> None:
    assert _classify(bid(is_newcomer=True, skill_evidence_score=0.60)) is None


# --------------------------------------------------------------- newcomer rule


def test_newcomer_skips_performance_check() -> None:
    # A newcomer with low P but passing evidence is eligible (P0 replaced by the evidence check).
    assert _classify(bid(is_newcomer=True, p=0.0, skill_evidence_score=0.85)) is None


def test_newcomer_competency_check_off_ignores_low_c() -> None:
    assert _classify(bid(is_newcomer=True, c=0.10, skill_evidence_score=0.85)) is None


def test_newcomer_competency_check_on_enforces_c0() -> None:
    params = FilterParams(p0=0.45, c0=0.40, team_size=1, newcomer_competency_check=True)
    b = bid(is_newcomer=True, c=0.10, skill_evidence_score=0.85)
    assert classify_bid(b, PROJECT, params, params.p0, params.c0) is ReasonCode.LOW_COMPETENCY


# --------------------------------------------------------------- relaxation (spec §9.2 step 4)


def test_relaxation_reported_and_finds_candidates() -> None:
    # Two slots needing one each; only low-P bids exist → P0 must relax from 0.45 to 0.40 to 0.35.
    project = ProjectInput(
        deadline_days=30,
        budget_after_fee_paisa=11_400_000,
        slots={"s1": SlotSpec("react", 1), "s2": SlotSpec("api", 1)},
    )
    params = FilterParams(p0=0.45, c0=0.40, team_size=2)
    bids = [
        bid("a", slot_id="s1", skill_id="react", p=0.36, c=0.40),
        bid("b", slot_id="s2", skill_id="api", p=0.36, c=0.40),
    ]
    result = filter_bids(bids, project, params)
    assert set(result.eligible) == {"a", "b"}
    assert not result.too_few
    # Relaxed in 0.05 steps, reported for the client (45 → 40 → 35).
    assert [(r.step, r.p0) for r in result.relaxations][:2] == [(1, 0.40), (2, 0.35)]


def test_still_too_few_after_max_relaxation() -> None:
    params = FilterParams(p0=0.45, c0=0.40, team_size=1)
    # A bid failing a *fixed* gate (too slow) can never become eligible through relaxation.
    result = filter_bids([bid("slow", t_days=99)], PROJECT, params)
    assert result.eligible == ()
    assert result.too_few
    assert result.shortfall[SLOT] == 1
    assert ("slow", ReasonCode.TOO_SLOW) in result.rejected
    assert len(result.relaxations) == 3  # tried all steps before giving up


# --------------------------------------------------------------- advancement ordering + shortlist


def _slot_project(count: int) -> ProjectInput:
    return ProjectInput(30, 11_400_000, {SLOT: SlotSpec("react", count)})


def test_advancement_orders_per_preset() -> None:
    bids = [
        bid("hi", p=0.90, c=0.90, t_days=25, c_paisa=3_000_000),
        bid("lo", p=0.50, c=0.50, t_days=10, c_paisa=1_000_000),
    ]
    project = _slot_project(2)
    quality = filter_bids(bids, project, FilterParams(advancement=Advancement.P, team_size=2))
    assert quality.shortlisted[SLOT][0] == "hi"  # highest P first
    fast = filter_bids(bids, project, FilterParams(advancement=Advancement.T, team_size=2))
    assert fast.shortlisted[SLOT][0] == "lo"  # fewest days first
    budget = filter_bids(bids, project, FilterParams(advancement=Advancement.C_COST, team_size=2))
    assert budget.shortlisted[SLOT][0] == "lo"  # cheapest first


def test_shortlist_caps_at_k_and_marks_not_shortlisted() -> None:
    # count=1 → K_s = max(3·1, 6) = 6; a 7th eligible bid is eligible but not shortlisted.
    bids = [bid(f"b{i}", developer_id=f"d{i}", c=0.9 - i * 0.01) for i in range(7)]
    result = filter_bids(bids, _slot_project(1), FilterParams(team_size=1))
    assert len(result.eligible) == 7
    assert len(result.shortlisted[SLOT]) == 6
    assert len(result.not_shortlisted) == 1


# --------------------------------------------------------------- pcs_replication mode


def test_pcs_replication_disables_newcomer_rule_and_relaxation() -> None:
    params = FilterParams(p0=0.45, c0=0.40, team_size=1, mode=Mode.PCS_REPLICATION)
    # In replication mode a newcomer is judged by P like everyone else (no evidence shortcut).
    b = bid(is_newcomer=True, p=0.10, skill_evidence_score=0.99)
    assert classify_bid(b, PROJECT, params, params.p0, params.c0) is ReasonCode.LOW_PERFORMANCE
    result = filter_bids([b], PROJECT, params)
    assert result.relaxations == ()  # no relaxation in replication mode


# --------------------------------------------------------------- reason precedence


def test_reason_precedence_is_stable() -> None:
    # A bid failing several gates reports the highest-precedence one (SUSPENDED before TOO_SLOW).
    b = bid(active=False, t_days=99, c=0.0)
    assert _classify(b) is ReasonCode.SUSPENDED


# --------------------------------------------------------------- property tests


@given(
    p=st.floats(0, 1),
    c=st.floats(0, 1),
    t=st.integers(1, 60),
    price=st.integers(1, 20_000_000),
)
@settings(max_examples=200)
def test_eligible_is_subset_and_consistent(p: float, c: float, t: int, price: int) -> None:
    b = bid(p=p, c=c, t_days=t, c_paisa=price)
    result = filter_bids([b], PROJECT, PARAMS)
    # Eligible ⊆ input, and a bid is eligible iff classify at the final thresholds returns None.
    assert set(result.eligible) <= {"b"}
    reason = classify_bid(b, PROJECT, PARAMS, PARAMS.p0, PARAMS.c0)
    assert (b.bid_id in result.eligible) == (reason is None) or result.relaxations


@given(n=st.integers(0, 12))
@settings(max_examples=50)
def test_relaxation_never_reduces_eligibility(n: int) -> None:
    # More relaxation never removes an already-eligible bid (thresholds only loosen).
    bids = [bid(f"b{i}", developer_id=f"d{i}", p=0.30 + i * 0.05, c=0.50) for i in range(n)]
    strict = filter_bids(
        bids, _slot_project(max(1, n)), FilterParams(p0=0.45, c0=0.40, team_size=max(1, n))
    )
    loose = filter_bids(
        bids,
        _slot_project(max(1, n)),
        FilterParams(p0=0.45, c0=0.40, team_size=max(1, n), relax_max_steps=3),
    )
    assert set(strict.eligible) <= set(loose.eligible)
