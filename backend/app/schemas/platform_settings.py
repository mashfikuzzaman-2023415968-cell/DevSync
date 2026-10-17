"""Typed, validated platform settings (spec §6.2).

All algorithm parameters live here, never hard-coded. Numeric weights are
`Decimal` (serialized as strings) so sums such as g1 + g2 + g3 = 1 are checked
exactly. Validation rules come from the paper's constraints (§9.1.2):
κ > 0.5, α_x and α_e < 0.5, weight groups sum to 1.

Keys added beyond the §6.2 table (DECISIONS.md D8): `rep.newcomer_review`,
`algorithm.mode`, `filter.newcomer_competency_check`, `filter.shortlist_min`,
`fitness.include_performance`, `fitness.use_skill_competency`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

D = Decimal
ONE = D(1)
HALF = D("0.5")


class _Group(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RepSettings(_Group):
    """Reputation model weights (Eq. 1–12) and our extensions."""

    alpha_comm: Decimal = Field(D("0.7"), ge=D(0), le=ONE, description="α, Eq. 2")
    alpha_team: Decimal = Field(D("0.7"), ge=D(0), le=ONE, description="α_m, Eq. 3")
    kappa_ext: Decimal = Field(D("0.7"), gt=HALF, le=ONE, description="κ_e, Eq. 5 (> 0.5)")
    kappa_int: Decimal = Field(D("0.7"), gt=HALF, le=ONE, description="κ_x, Eq. 6 (> 0.5)")
    alpha_x: Decimal = Field(D("0.3"), ge=D(0), lt=HALF, description="α_x, Eq. 7 (< 0.5)")
    alpha_e: Decimal = Field(D("0.3"), ge=D(0), lt=HALF, description="α_e, Eq. 8 (< 0.5)")
    w_internal: Decimal = Field(D("0.8"), ge=D(0), le=ONE, description="w_y, Eq. 9")
    w_external: Decimal = Field(D("0.2"), ge=D(0), le=ONE, description="w_x, Eq. 9")
    f_default: Decimal = Field(D("0.7"), ge=D(0), le=ONE, description="f, Eq. 4")
    g: tuple[Decimal, Decimal, Decimal] = (D("0.5"), D("0.25"), D("0.25"))
    gamma0_base: Decimal = Field(D("0.40"), ge=D(0), le=ONE)
    gamma0_per_verification: Decimal = Field(D("0.05"), ge=D(0), le=ONE)
    gamma0_max: Decimal = Field(D("0.60"), ge=D(0), le=ONE)
    neutral: Decimal = Field(D("0.5"), ge=D(0), le=ONE)
    newcomer_review: Decimal | None = Field(
        None, ge=D(0), le=ONE, description="β for developers with no reviews; None = platform mean"
    )
    newcomer_review_fallback: Decimal = Field(D("0.6"), ge=D(0), le=ONE)
    max_change_per_project: Decimal = Field(D("0.15"), gt=D(0), le=ONE)

    @model_validator(mode="after")
    def _sums(self) -> Self:
        if self.w_internal + self.w_external != ONE:
            raise ValueError("rep.w_internal + rep.w_external must equal 1")
        if any(x < 0 for x in self.g) or sum(self.g) != ONE:
            raise ValueError("rep.g (g1, g2, g3) must be non-negative and sum to 1")
        if self.gamma0_base > self.gamma0_max:
            raise ValueError("rep.gamma0_base must not exceed rep.gamma0_max")
        return self


class NewcomerSettings(_Group):
    """Who counts as a newcomer and what skill score passes filtering."""

    threshold: int = Field(3, ge=1, le=20)
    pass_mark: Decimal = Field(D("0.60"), ge=D(0), le=ONE)


class FilterSettings(_Group):
    """Algorithm 1 thresholds and shortlist size (§9.2)."""

    P0: Decimal = Field(D("0.45"), ge=D(0), le=ONE)
    C0: Decimal = Field(D("0.40"), ge=D(0), le=ONE)
    shortlist_factor: int = Field(3, ge=1, le=10, description="K_s = max(factor·count_s, min)")
    shortlist_min: int = Field(6, ge=1, le=50)
    relax_step: Decimal = Field(D("0.05"), gt=D(0), le=D("0.2"))
    relax_max_steps: int = Field(3, ge=0, le=10)
    newcomer_competency_check: bool = False


class PsoSettings(_Group):
    """Binary PSO parameters (Algorithm 2, §9.3); bounded per §15.4."""

    particles: int = Field(30, ge=2, le=50)
    max_iter: int = Field(200, ge=1, le=400)
    z1: Decimal = Field(D("1.5"), ge=D(0), le=D(4))
    z2: Decimal = Field(D("1.5"), ge=D(0), le=D(4))
    inertia: Decimal = Field(D("1.0"), ge=D(0), le=D(2))
    v_max: Decimal = Field(D("4.0"), gt=D(0), le=D(10))
    bounds: tuple[Decimal, Decimal] = (D(-1), D(1))
    early_stop_iters: int = Field(40, ge=1, le=400)
    timeout_seconds: int = Field(10, ge=1, le=60)

    @model_validator(mode="after")
    def _bounds(self) -> Self:
        if self.bounds[0] >= self.bounds[1]:
            raise ValueError("pso.bounds must satisfy b_l < b_u")
        return self


class ExactSettings(_Group):
    """Exact solver limits (§9.4)."""

    max_candidates: int = Field(18, ge=1, le=20)
    max_combinations: int = Field(2_000_000, ge=1, le=5_000_000)


class FairnessSettings(_Group):
    """Fairness dial default (1 when eligible newcomers exist, else 0)."""

    default_min_newcomers: int = Field(1, ge=0, le=10)


class FitnessSettings(_Group):
    """Optional fitness variants (A7, §9.1.7); both off by default."""

    include_performance: bool = False
    use_skill_competency: bool = False


class PaySettings(_Group):
    """Payment policy (Eq. 20–23) and money rules."""

    platform_fee_bp: int = Field(500, ge=0, le=10_000)
    bonus_pool_bp: int = Field(1000, ge=0, le=10_000)
    q_max: Decimal = Field(D("0.25"), gt=D(0), le=ONE)
    theta1: Decimal = Field(D("4"), gt=D(0), le=D(50))
    theta2: Decimal = Field(D("4"), gt=D(0), le=D(50))
    auto_approve_days: int = Field(7, ge=1, le=60)


class InviteSettings(_Group):
    """Invitation expiry."""

    expiry_hours: int = Field(48, ge=1, le=24 * 14)


class SplitSettings(_Group):
    """Contribution split objection window."""

    objection_hours: int = Field(72, ge=1, le=24 * 14)


class ReviewSettings(_Group):
    """Review and contest windows."""

    window_days: int = Field(7, ge=1, le=60)
    contest_days: int = Field(14, ge=1, le=90)


class TrustSettings(_Group):
    """Reviewer trust formula coefficients (§9.14)."""

    age_weight: Decimal = Field(D("0.25"), ge=D(0), le=ONE)
    age_full_days: int = Field(90, ge=1, le=3650)
    completed_weight: Decimal = Field(D("0.25"), ge=D(0), le=ONE)
    completed_full: int = Field(5, ge=1, le=100)
    verified_weight: Decimal = Field(D("0.15"), ge=D(0), le=ONE)
    consistency_weight: Decimal = Field(D("0.35"), ge=D(0), le=ONE)
    min_trust: Decimal = Field(D("0.1"), ge=D(0), le=ONE)
    open_flag_factor: Decimal = Field(D("0.5"), ge=D(0), le=ONE)
    bayes_m: int = Field(3, ge=0, le=100)

    @model_validator(mode="after")
    def _sum(self) -> Self:
        total = (
            self.age_weight + self.completed_weight + self.verified_weight + self.consistency_weight
        )
        if total != ONE:
            raise ValueError("trust weights must sum to 1")
        return self


class ConsistencySettings(_Group):
    """Review vs evidence mismatch threshold."""

    threshold: Decimal = Field(D("0.4"), ge=D(0), le=ONE)


class AlertSettings(_Group):
    """Inactivity, repair-suggestion and stalled-task thresholds (days)."""

    inactive_days: int = Field(7, ge=1, le=60)
    repair_days: int = Field(10, ge=1, le=60)
    stalled_days: int = Field(5, ge=1, le=60)


class BiddingSettings(_Group):
    """Too-few-bids handling (§9.19)."""

    min_bids_factor: Decimal = Field(D("1.0"), ge=D(0), le=D(10))
    extend_days: int = Field(3, ge=1, le=30)
    max_extensions: int = Field(2, ge=0, le=5)


class RateRule(_Group):
    """At most `limit` requests per `window_seconds` (sliding window)."""

    limit: int = Field(ge=1, le=100_000)
    window_seconds: int = Field(ge=1, le=7 * 86_400)


def _rules(*pairs: tuple[int, int]) -> tuple[RateRule, ...]:
    return tuple(RateRule(limit=limit, window_seconds=window) for limit, window in pairs)


MINUTE, HOUR, DAY = 60, 3600, 86_400


class RateLimitSettings(_Group):
    """Application rate limits (spec §14.8). Each scope may combine several windows."""

    api_authenticated: tuple[RateRule, ...] = _rules((120, MINUTE))
    api_anonymous: tuple[RateRule, ...] = _rules((60, MINUTE))
    login: tuple[RateRule, ...] = _rules((5, MINUTE), (20, HOUR))
    registration: tuple[RateRule, ...] = _rules((5, HOUR))
    otp_send: tuple[RateRule, ...] = _rules((1, MINUTE), (5, HOUR))
    otp_verify: tuple[RateRule, ...] = _rules((10, HOUR))
    password_reset: tuple[RateRule, ...] = _rules((3, HOUR))
    email_resend: tuple[RateRule, ...] = _rules((3, HOUR))
    totp: tuple[RateRule, ...] = _rules((5, 5 * MINUTE))
    captcha_challenge: tuple[RateRule, ...] = _rules((30, MINUTE))
    # Phase 2 (DECISIONS D22): homepage stats are cached, so a generous read limit; error
    # reports are small and few per page view.
    public_stats: tuple[RateRule, ...] = _rules((60, MINUTE))
    client_errors: tuple[RateRule, ...] = _rules((10, MINUTE), (50, HOUR))
    bid: tuple[RateRule, ...] = _rules((20, HOUR))
    project_create: tuple[RateRule, ...] = _rules((10, DAY))
    formation_run: tuple[RateRule, ...] = _rules((10, HOUR))
    test_start: tuple[RateRule, ...] = _rules((10, HOUR))
    coding_submit: tuple[RateRule, ...] = _rules((10, HOUR))
    coding_practice: tuple[RateRule, ...] = _rules((30, HOUR))
    comment: tuple[RateRule, ...] = _rules((60, HOUR))
    review: tuple[RateRule, ...] = _rules((30, HOUR))
    dispute: tuple[RateRule, ...] = _rules((5, DAY))
    upload: tuple[RateRule, ...] = _rules((20, HOUR))
    github_sync: tuple[RateRule, ...] = _rules((1, 10 * MINUTE))
    data_export: tuple[RateRule, ...] = _rules((2, DAY))
    admin: tuple[RateRule, ...] = _rules((300, MINUTE))
    sse_concurrent: int = Field(3, ge=1, le=20)
    login_captcha_after_failures: int = Field(3, ge=1, le=20)
    login_progressive_after_failures: int = Field(5, ge=1, le=50)
    login_lock_after_failures: int = Field(10, ge=2, le=100)
    login_lock_minutes: int = Field(15, ge=1, le=1440)


class AlgorithmSettings(_Group):
    """`devsync` (product) or `pcs_replication` (paper only, §9.0)."""

    mode: Literal["devsync", "pcs_replication"] = "devsync"


class PlatformSettingsValues(_Group):
    """The full settings document stored in `platform_settings.values`."""

    rep: RepSettings = RepSettings()
    newcomer: NewcomerSettings = NewcomerSettings()
    filter: FilterSettings = FilterSettings()
    pso: PsoSettings = PsoSettings()
    exact: ExactSettings = ExactSettings()
    fairness: FairnessSettings = FairnessSettings()
    fitness: FitnessSettings = FitnessSettings()
    pay: PaySettings = PaySettings()
    invite: InviteSettings = InviteSettings()
    split: SplitSettings = SplitSettings()
    review: ReviewSettings = ReviewSettings()
    trust: TrustSettings = TrustSettings()
    consistency: ConsistencySettings = ConsistencySettings()
    alerts: AlertSettings = AlertSettings()
    bidding: BiddingSettings = BiddingSettings()
    algorithm: AlgorithmSettings = AlgorithmSettings()
    ratelimit: RateLimitSettings = RateLimitSettings()


def default_settings_document() -> dict[str, object]:
    """Defaults as JSON-compatible data (Decimals become strings)."""
    return PlatformSettingsValues().model_dump(mode="json")
