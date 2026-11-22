"""Reviewer trust (spec §9.14 formula) and trust-weighted means, by hand."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.algorithms.filtering import Mode
from app.algorithms.trust import Reviewer, TrustParams, reviewer_trust, weighted_mean

D = Decimal  # short alias for the many decimal literals below
pytestmark = pytest.mark.unit


def test_trust_formula_by_hand() -> None:
    """45 days (0.25·0.5 = 0.125) + 5 projects (0.25·1) + verified (0.15) + consistency 0.8
    (0.35·0.8 = 0.28) = 0.805."""
    assert reviewer_trust(Reviewer(45, 5, True, D("0.8"))) == D("0.805")


def test_trust_saturates_and_floors() -> None:
    """Everything at maximum → 1; a brand-new unverified account → floor 0.1 (never 0)."""
    assert reviewer_trust(Reviewer(900, 50, True, D(1))) == D(1)
    assert reviewer_trust(Reviewer(0, 0, False, D(0))) == D("0.1")


def test_trust_flags() -> None:
    """Open flag halves trust (0.805 → 0.4025); a confirmed colluder weighs 0."""
    assert reviewer_trust(Reviewer(45, 5, True, D("0.8"), open_flag=True)) == D("0.4025")
    assert reviewer_trust(Reviewer(45, 5, True, D("0.8"), confirmed_colluder=True)) == 0


def test_trust_uses_settings_coefficients() -> None:
    prm = TrustParams(age_weight=D(0), completed_weight=D(0), verified_weight=D(1),
                      consistency_weight=D(0))  # fmt: skip
    assert reviewer_trust(Reviewer(0, 0, True, D(0)), prm) == D(1)


def test_trust_refuses_invalid_reviewer() -> None:
    with pytest.raises(ValueError, match="negative"):
        reviewer_trust(Reviewer(-1, 0, False, D(0)))
    with pytest.raises(ValueError, match="between 0 and 1"):
        reviewer_trust(Reviewer(1, 0, False, D("1.5")))


def test_weighted_mean_by_hand() -> None:
    """(1.0 × 0.9 + 0.5 × 0.1) / (0.9 + 0.1) = 0.95."""
    assert weighted_mean([D(1), D("0.5")], [D("0.9"), D("0.1")]) == D("0.95")


def test_weighted_mean_replication_ignores_trust() -> None:
    """pcs_replication has no evidence-based weighting: plain mean (1 + 0.5)/2 = 0.75."""
    assert weighted_mean([D(1), D("0.5")], [D("0.9"), D("0.1")], Mode.PCS_REPLICATION) == D("0.75")


def test_weighted_mean_nothing_to_average() -> None:
    """No values, or only zero weights (colluders) → None ("no review"), never a made-up value."""
    assert weighted_mean([], []) is None
    assert weighted_mean([D("0.9")], [D(0)]) is None


def test_weighted_mean_refuses_bad_input() -> None:
    with pytest.raises(ValueError, match="same length"):
        weighted_mean([D(1)], [])
    with pytest.raises(ValueError, match="between 0 and 1"):
        weighted_mean([D("1.5")], [D(1)])
    with pytest.raises(ValueError, match="negative"):
        weighted_mean([D("0.5")], [D(-1)])
