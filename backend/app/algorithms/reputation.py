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


@dataclass(frozen=True)
class NewcomerParams:
    """The `rep.*` platform settings the starting values use (§6.2); defaults equal the spec's.

    The service passes the active settings, so an admin change takes effect without a deploy;
    the defaults exist only so tests and the seed can call this with the spec's values."""

    f: Decimal = Decimal("0.7")  # rep.f_default, Eq. 4
    g: tuple[Decimal, Decimal, Decimal] = (Decimal("0.5"), Decimal("0.25"), Decimal("0.25"))
    gamma0_base: Decimal = Decimal("0.40")  # rep.gamma0_base
    gamma0_per_verification: Decimal = Decimal("0.05")  # rep.gamma0_per_verification
    gamma0_max: Decimal = Decimal("0.60")  # rep.gamma0_max
    neutral: Decimal = Decimal("0.5")  # rep.neutral: Γ_m⁰, μ and T with no history


# ω⁰ = min(0.5, 0.2 × D) is fixed by §9.1.3 (no setting key names it).
_OMEGA0_PER_DOMAIN = Decimal("0.2")
_OMEGA0_MAX = Decimal("0.5")


def newcomer_snapshot(inp: NewcomerInputs, params: NewcomerParams | None = None) -> Snapshot:
    """Starting reputation for a developer with no completed projects (spec §9.1.3).

    Γ⁰ = min(gamma0_max, gamma0_base + gamma0_per_verification × verified items) (0.60, 0.40,
    0.05 by default); Γ_m⁰ = neutral; ω⁰ = min(0.5, 0.2 × evidence domains); μ = T = neutral;
    β = newcomer_review. X = Γ⁰ and X_m = Γ_m⁰ (Eq. 2/3 at n = 0). Then C = f·ω + (1−f)·X
    (Eq. 4) and P = g1·β + g2·μ + g3·T (Eq. 12) with the `rep.*` weights.
    """
    prm = params or NewcomerParams()
    gamma0 = min(prm.gamma0_max, prm.gamma0_base + prm.gamma0_per_verification * inp.verified_items)
    gamma_m0 = prm.neutral
    omega = min(_OMEGA0_MAX, _OMEGA0_PER_DOMAIN * inp.evidence_domains)
    mu = prm.neutral
    t = prm.neutral
    beta = inp.newcomer_review_beta
    x = gamma0
    xm = gamma_m0
    g1, g2, g3 = prm.g
    c = prm.f * omega + (Decimal(1) - prm.f) * x
    p = g1 * beta + g2 * mu + g3 * t
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
