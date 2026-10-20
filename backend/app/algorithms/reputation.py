"""Reputation — newcomer starting values only (spec §9.1.3, A4/A9). PURE.

The full [PCS] reputation engine (Eq. 1–12) is Phase 6. Phase 5 needs just the starting values
for a newcomer so Algorithm 1 has a `P` and `C` to work with. `compute_snapshot(history, …)` and
the equation functions arrive in Phase 6; keeping this file to `newcomer_snapshot()` makes that
split explicit. All scores are on 0–1; arithmetic uses `Decimal` (the snapshot columns are
`numeric(4,3)`), so values are exact and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_Q = Decimal("0.001")  # snapshot precision (numeric(4,3))


def _q(value: Decimal) -> Decimal:
    return value.quantize(_Q, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class NewcomerInputs:
    """What a newcomer snapshot needs (built by the service / seed from verified evidence)."""

    verified_items: int  # of {phone, email, complete profile, verified certificate} (0–4)
    evidence_domains: int  # distinct domains with skill-evidence score ≥ newcomer.pass_mark
    newcomer_review_beta: Decimal  # rep.newcomer_review (platform mean β, fallback 0.6)


@dataclass(frozen=True)
class Snapshot:
    """The §9.1.7 output shape, as Decimals for exact storage."""

    omega: Decimal
    x: Decimal
    xm: Decimal
    beta: Decimal
    mu: Decimal
    t: Decimal
    c: Decimal
    p: Decimal
    completed_projects: int
    distinct_clients: int


# Default reputation weights (spec §9.1.2 / §6.2): C = f·ω + (1−f)·X; P = g1·β + g2·μ + g3·T.
_F = Decimal("0.7")
_G1, _G2, _G3 = Decimal("0.5"), Decimal("0.25"), Decimal("0.25")


def newcomer_snapshot(inp: NewcomerInputs) -> Snapshot:
    """Starting reputation for a developer with no completed projects (spec §9.1.3).

    Γ⁰ = min(0.60, 0.40 + 0.05 × verified items); Γ_m⁰ = 0.5; ω⁰ = min(0.5, 0.2 × evidence
    domains); μ = T = 0.5; β = newcomer_review. X = Γ⁰ and X_m = Γ_m⁰ (Eq. 2/3 at n = 0). Then
    C (Eq. 4) and P (Eq. 12) with the default weights.
    """
    gamma0 = min(Decimal("0.60"), Decimal("0.40") + Decimal("0.05") * inp.verified_items)
    gamma_m0 = Decimal("0.5")
    omega = min(Decimal("0.5"), Decimal("0.2") * inp.evidence_domains)
    mu = Decimal("0.5")
    t = Decimal("0.5")
    beta = inp.newcomer_review_beta
    x = gamma0
    xm = gamma_m0
    c = _F * omega + (Decimal(1) - _F) * x
    p = _G1 * beta + _G2 * mu + _G3 * t
    return Snapshot(
        omega=_q(omega),
        x=_q(x),
        xm=_q(xm),
        beta=_q(beta),
        mu=_q(mu),
        t=_q(t),
        c=_q(c),
        p=_q(p),
        completed_projects=0,
        distinct_clients=0,
    )
