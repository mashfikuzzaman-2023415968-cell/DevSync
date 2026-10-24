"""Values that come from the platform settings, not from literals (spec §6.2: "all algorithm
parameters live here, never hard-coded"): `bidding.min_bids_factor` in Algorithm 1's "enough
bids" test, and the `rep.*` weights in the newcomer starting values (§9.1.3). Pure."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.algorithms.filtering import (
    Advancement,
    BidInput,
    FilterParams,
    ProjectInput,
    SlotSpec,
    filter_bids,
    required_bids,
)
from app.algorithms.reputation import NewcomerInputs, NewcomerParams, newcomer_snapshot
from app.schemas.platform_settings import PlatformSettingsValues, RepSettings
from app.services.reputation_read import newcomer_params

D = Decimal
SLOT = "slot"
PROJECT = ProjectInput(
    deadline_days=30, budget_after_fee_paisa=10_000_000, slots={SLOT: SlotSpec("s", 2)}
)


def _bid(i: int) -> BidInput:
    return BidInput(
        bid_id=f"b{i}",
        slot_id=SLOT,
        skill_id="s",
        developer_id=f"d{i}",
        is_newcomer=False,
        p=0.8,
        c=0.8,
        t_days=10,
        c_paisa=100_000,
        skill_evidence_score=None,
        has_slot_skill=True,
        active=True,
        available=True,
        self_dealing=False,
    )


def _params(factor: str) -> FilterParams:
    return FilterParams(advancement=Advancement.C, team_size=2, min_bids_factor=D(factor))


# --------------------------------------------------------------------------- min_bids_factor


@pytest.mark.parametrize(
    ("places", "factor", "needed"),
    [
        (2, "1.0", 2),  # the spec default: as many eligible bids as places
        (2, "1.5", 3),
        (2, "2", 4),
        (10, "1.1", 11),  # exact in Decimal (a float would give 12)
        (3, "1.01", 4),  # any fraction rounds up
        (2, "0.5", 2),  # never fewer than the places: a team can't form short
        (2, "0", 2),
    ],
)
def test_required_bids(places: int, factor: str, needed: int) -> None:
    assert required_bids(places, D(factor)) == needed


def test_default_factor_two_bids_for_two_places_is_enough() -> None:
    result = filter_bids([_bid(1), _bid(2)], PROJECT, _params("1.0"))
    assert not result.too_few
    assert result.shortfall == {SLOT: 0}


def test_a_higher_factor_asks_for_more_competition() -> None:
    result = filter_bids([_bid(1), _bid(2)], PROJECT, _params("1.5"))
    assert result.too_few
    assert result.shortfall == {SLOT: 1}  # ⌈1.5 × 2⌉ = 3 needed, 2 eligible


def test_the_boundary_bid_meets_a_higher_factor() -> None:
    result = filter_bids([_bid(1), _bid(2), _bid(3)], PROJECT, _params("1.5"))
    assert not result.too_few
    assert result.shortfall == {SLOT: 0}


def test_a_higher_factor_relaxes_further_before_giving_up() -> None:
    # Two bids pass the default minimums, a third only after one relaxation step: with factor
    # 1.5 the filter relaxes to let the third in, with 1.0 it doesn't need to.
    weak = BidInput(**{**_bid(3).__dict__, "p": 0.41})
    bids = [_bid(1), _bid(2), weak]
    assert filter_bids(bids, PROJECT, _params("1.0")).relaxations == ()
    relaxed = filter_bids(bids, PROJECT, _params("1.5"))
    assert [r.step for r in relaxed.relaxations] == [1]
    assert not relaxed.too_few


# --------------------------------------------------------------------------- newcomer rep.*


INPUTS = NewcomerInputs(verified_items=2, evidence_domains=1, newcomer_review_beta=D("0.6"))


def test_defaults_are_the_spec_values() -> None:
    assert newcomer_snapshot(INPUTS) == newcomer_snapshot(INPUTS, NewcomerParams())
    s = newcomer_snapshot(INPUTS)
    # Γ⁰ = 0.40 + 0.05 × 2 = 0.50; ω⁰ = 0.2; C = 0.7·0.2 + 0.3·0.5 = 0.29;
    # P = 0.5·0.6 + 0.25·0.5 + 0.25·0.5 = 0.55.
    assert (s.x, s.omega, s.c, s.p) == (D("0.500"), D("0.200"), D("0.290"), D("0.550"))


def test_competency_weight_f_comes_from_the_params() -> None:
    s = newcomer_snapshot(INPUTS, NewcomerParams(f=D("0.5")))
    assert s.c == D("0.350")  # 0.5·0.2 + 0.5·0.5


def test_performance_weights_g_come_from_the_params() -> None:
    s = newcomer_snapshot(INPUTS, NewcomerParams(g=(D("1"), D("0"), D("0"))))
    assert s.p == D("0.600")  # β alone


def test_gamma0_settings_and_cap() -> None:
    prm = NewcomerParams(
        gamma0_base=D("0.30"), gamma0_per_verification=D("0.10"), gamma0_max=D("0.45")
    )
    assert newcomer_snapshot(INPUTS, prm).x == D("0.450")  # 0.30 + 0.20 capped at 0.45
    none = NewcomerInputs(verified_items=0, evidence_domains=0, newcomer_review_beta=D("0.6"))
    assert newcomer_snapshot(none, prm).x == D("0.300")


def test_neutral_sets_teamwork_punctuality_and_reliability() -> None:
    s = newcomer_snapshot(INPUTS, NewcomerParams(neutral=D("0.4")))
    assert (s.xm, s.mu, s.t) == (D("0.400"), D("0.400"), D("0.400"))


def test_the_service_maps_the_active_settings() -> None:
    settings = PlatformSettingsValues(
        rep=RepSettings(
            f_default=D("0.6"),
            g=(D("0.6"), D("0.2"), D("0.2")),
            gamma0_base=D("0.35"),
            gamma0_per_verification=D("0.04"),
            gamma0_max=D("0.55"),
            neutral=D("0.45"),
        )
    )
    assert newcomer_params(settings) == NewcomerParams(
        f=D("0.6"),
        g=(D("0.6"), D("0.2"), D("0.2")),
        gamma0_base=D("0.35"),
        gamma0_per_verification=D("0.04"),
        gamma0_max=D("0.55"),
        neutral=D("0.45"),
    )
