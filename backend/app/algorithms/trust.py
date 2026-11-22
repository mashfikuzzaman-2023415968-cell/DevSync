"""Reviewer trust and trust-weighted review means (spec §9.14, formula only; D90). PURE.

    trust(u) = clamp(0.1, 1, 0.25·min(1, age_days/90) + 0.25·min(1, completed/5)
                              + 0.15·verified + 0.35·consistency_history)
               × 0 if a confirmed colluder  × 0.5 if an open integrity flag

Phase 6 uses it to weigh the simulated reviews that become the rating slots of Eq. 2/3/6
(§9.1.1: "already trust-weighted"). The integrity rules that *raise* flags, consistency checks,
trimming and the `reviewer_trust` table are Phase 11. Coefficients come from `trust.*` settings.
`pcs_replication` has no evidence-based weighting (§9.0), so there every review weighs 1.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.algorithms.filtering import Mode

ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True)
class TrustParams:
    """The `trust.*` settings (§6.2, DECISIONS D8); defaults equal the spec's."""

    age_weight: Decimal = Decimal("0.25")
    age_full_days: int = 90
    completed_weight: Decimal = Decimal("0.25")
    completed_full: int = 5
    verified_weight: Decimal = Decimal("0.15")
    consistency_weight: Decimal = Decimal("0.35")
    min_trust: Decimal = Decimal("0.1")
    open_flag_factor: Decimal = Decimal("0.5")


@dataclass(frozen=True)
class Reviewer:
    """What the trust formula knows about a reviewer (built by the service or the simulator)."""

    age_days: int
    completed: int
    verified: bool
    consistency_history: Decimal  # 0–1: share of past reviews consistent with evidence
    confirmed_colluder: bool = False
    open_flag: bool = False


def reviewer_trust(reviewer: Reviewer, params: TrustParams | None = None) -> Decimal:
    """§9.14 trust of one reviewer, in [0, 1] (0 only for a confirmed colluder)."""
    prm = params or TrustParams()
    if reviewer.age_days < 0 or reviewer.completed < 0:
        raise ValueError("age and completed projects must not be negative")
    if not ZERO <= reviewer.consistency_history <= ONE:
        raise ValueError("consistency history must be between 0 and 1")
    raw = (
        prm.age_weight * min(ONE, Decimal(reviewer.age_days) / Decimal(prm.age_full_days))
        + prm.completed_weight * min(ONE, Decimal(reviewer.completed) / Decimal(prm.completed_full))
        + prm.verified_weight * (ONE if reviewer.verified else ZERO)
        + prm.consistency_weight * reviewer.consistency_history
    )
    value = max(prm.min_trust, min(ONE, raw))
    if reviewer.confirmed_colluder:
        return ZERO
    if reviewer.open_flag:
        return value * prm.open_flag_factor
    return value


def weighted_mean(
    values: Sequence[Decimal], weights: Sequence[Decimal], mode: Mode = Mode.DEVSYNC
) -> Decimal | None:
    """Trust-weighted mean of normalised ratings (0–1). In `pcs_replication` every weight is 1.

    Returns None when nothing can be averaged (no values, or every weight 0 — e.g. only
    colluders), so the caller treats it as "no review" instead of inventing a value."""
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")
    for v in values:
        if not ZERO <= v <= ONE:
            raise ValueError("ratings must be between 0 and 1")
    if any(w < 0 for w in weights):
        raise ValueError("weights must not be negative")
    used = [ONE] * len(values) if mode is Mode.PCS_REPLICATION else list(weights)
    total = sum(used, ZERO)
    if total == 0:
        return None
    return sum((v * w for v, w in zip(values, used, strict=True)), ZERO) / total
