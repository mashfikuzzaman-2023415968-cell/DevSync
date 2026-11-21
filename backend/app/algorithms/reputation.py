"""Reputation — newcomer starting values only (spec §9.1.3, A4/A9). PURE.

The full [PCS] reputation engine (Eq. 1–12) is Phase 6. Phase 5 needs just the starting values
for a newcomer so Algorithm 1 has a `P` and `C` to work with. `compute_snapshot(history, …)` and
the equation functions arrive in Phase 6; keeping this file to `newcomer_snapshot()` makes that
split explicit. All scores are on 0–1; arithmetic uses `Decimal` (the snapshot columns are
`numeric(4,3)`), so values are exact and reproducible.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.algorithms.filtering import Mode

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


# =========================================================================== Phase 6: Eq. 1–12
#
# The [PCS] equations, one function each (spec §9.1.2), then `compute_snapshot()`, which walks a
# developer's completed projects oldest first. Arithmetic is `Decimal` throughout; only stored
# outputs are rounded (half-up, 3 places, D85). `pcs_replication` switches off the DevSync
# extensions (change cap, §9.1.3 starting values, per-skill competency) and keeps the A2 clip; the
# values the paper leaves undefined (ω and μ below two projects, β with no reviews, the starting
# Γ⁰ and Γ_m⁰) are 0 there, the paper's "set to zero" (D89).

ZERO = Decimal(0)
ONE = Decimal(1)
FORMULA_VERSION = 1  # stored in reputation_log; bump when an equation's implementation changes
MIN_PROJECTS_FOR_DIVERSITY = 2  # Eq. 1 and Eq. 10 divide by N(N − 1) (A9 below that)


def _unit(value: Decimal, name: str) -> Decimal:
    """Refuse a score outside [0, 1]: fail closed, a bad input never becomes a reputation."""
    if not ZERO <= value <= ONE:
        raise ValueError(f"{name} must be between 0 and 1, got {value}")
    return value


def eq01_omega(domain_counts: Mapping[str, int]) -> Decimal:
    """Eq. 1 — expertise and diversity: Simpson's index over the domains of N_i projects.

    ω_i = 1 − Σ_l n_i^l (n_i^l − 1) / (N_i (N_i − 1)). Defined for N_i ≥ 2 only; below that the
    caller uses the newcomer value (A9, D88)."""
    if any(n < 0 for n in domain_counts.values()):
        raise ValueError("domain counts must not be negative")
    total = sum(domain_counts.values())
    if total < MIN_PROJECTS_FOR_DIVERSITY:
        raise ValueError("Eq. 1 needs at least two projects (A9)")
    same = sum(n * (n - 1) for n in domain_counts.values())
    return ONE - Decimal(same) / Decimal(total * (total - 1))


def eq02_communication(gamma: Decimal, previous: Decimal, alpha: Decimal) -> Decimal:
    """Eq. 2 — communication, one EWMA step: X_i^n = α·Γ_i^n + (1 − α)·X_i^(n−1), X_i^0 = Γ_i^0."""
    return alpha * _unit(gamma, "Γ") + (ONE - alpha) * _unit(previous, "X")


def eq03_teamwork(gamma_m: Decimal, previous: Decimal, alpha_m: Decimal) -> Decimal:
    """Eq. 3 — teamwork capacity, one EWMA step: X_m^n = α_m·Γ_m^n + (1 − α_m)·X_m^(n−1)."""
    return alpha_m * _unit(gamma_m, "Γ_m") + (ONE - alpha_m) * _unit(previous, "X_m")


def eq04_competency(omega: Decimal, x: Decimal, f: Decimal) -> Decimal:
    """Eq. 4 — competency C_i = f·ω_i + (1 − f)·X_i (A5: the weights f and 1 − f sum to 1)."""
    return f * _unit(omega, "ω") + (ONE - f) * _unit(x, "X")


def _ewma_first(values: Sequence[Decimal], weight: Decimal, name: str) -> Decimal:
    """s_1 = v_1; s_t = w·v_t + (1 − w)·s_(t−1). The final s is the project's value."""
    if not values:
        raise ValueError(f"{name} needs at least one rating")
    state = _unit(values[0], name)
    for value in values[1:]:
        state = weight * _unit(value, name) + (ONE - weight) * state
    return state


def eq05_external_within(slots: Sequence[Decimal], kappa_e: Decimal) -> Decimal:
    """Eq. 5 — external reviews within one project, time slots t = 1…:
    E_(1,i)^1 = E_i^1 ;  E_(1,i)^t = κ_e·E_i^t + (1 − κ_e)·E_(1,i)^(t−1), κ_e > 0.5."""
    return _ewma_first(slots, kappa_e, "external review")


def eq06_internal_within(slots: Sequence[Decimal], kappa_x: Decimal) -> Decimal:
    """Eq. 6 — internal reviews within one project (milestone ratings, then the final review):
    I_(1,i)^1 = I_i^1 ;  I_(1,i)^t = κ_x·I_i^t + (1 − κ_x)·I_(1,i)^(t−1), κ_x > 0.5."""
    return _ewma_first(slots, kappa_x, "internal review")


def eq07_internal_across(previous: Decimal | None, current: Decimal, alpha_x: Decimal) -> Decimal:
    """Eq. 7 — internal reviews across projects: λ_(1,i) = I_(1,i);
    λ_(n,i) = α_x·I_(n,i) + (1 − α_x)·λ_(n−1,i), α_x < 0.5 so older projects weigh more (A6)."""
    if previous is None:
        return _unit(current, "I")
    return alpha_x * _unit(current, "I") + (ONE - alpha_x) * _unit(previous, "λ")


def eq08_external_across(previous: Decimal | None, current: Decimal, alpha_e: Decimal) -> Decimal:
    """Eq. 8 — external reviews across projects: ε_(1,i) = E_(1,i);
    ε_(n,i) = α_e·E_(n,i) + (1 − α_e)·ε_(n−1,i), α_e < 0.5 (A6). Runs over the projects that
    have verified external reviews, in order (D87)."""
    if previous is None:
        return _unit(current, "E")
    return alpha_e * _unit(current, "E") + (ONE - alpha_e) * _unit(previous, "ε")


def eq09_beta(lam: Decimal, eps: Decimal | None, w_y: Decimal, w_x: Decimal) -> Decimal:
    """Eq. 9 — project review β_i = w_y·λ_(n,i) + w_x·ε_(n,i), w_y + w_x = 1.
    With no verified external reviews, β_i = λ_(n,i) (A8)."""
    if eps is None:
        return _unit(lam, "λ")
    return w_y * _unit(lam, "λ") + w_x * _unit(eps, "ε")


def eq10_mu(client_counts: Mapping[str, int]) -> Decimal:
    """Eq. 10 — re-employment diversity over clients (Simpson's index):
    μ_i = 1 − Σ_j φ_(i,j)(φ_(i,j) − 1) / (N_i^r (N_i^r − 1)). Defined for N_i^r ≥ 2 (A9)."""
    if any(n < 0 for n in client_counts.values()):
        raise ValueError("client counts must not be negative")
    total = sum(client_counts.values())
    if total < MIN_PROJECTS_FOR_DIVERSITY:
        raise ValueError("Eq. 10 needs at least two hires (A9)")
    same = sum(n * (n - 1) for n in client_counts.values())
    return ONE - Decimal(same) / Decimal(total * (total - 1))


def eq11_timeliness(durations: Sequence[tuple[int, int]], *, clip: bool = True) -> Decimal:
    """Eq. 11 — timeliness T_i = 1 − (1/n) Σ_n min(t_(n,i) / T_j^d, 1).

    Implemented as written, so faster work gives a higher T (A1). The paper assumes t ≤ T^d; with
    `clip` (A2, default, kept in replication) each ratio is capped at 1, so late work contributes
    0 instead of pushing T below 0. `clip=False` exists only to show the alternative in tests."""
    if not durations:
        raise ValueError("Eq. 11 needs at least one project")
    total = ZERO
    for t_days, deadline in durations:
        if t_days < 0 or deadline <= 0:
            raise ValueError("t must be ≥ 0 and T^d > 0")
        ratio = Decimal(t_days) / Decimal(deadline)
        total += min(ratio, ONE) if clip else ratio
    return ONE - total / Decimal(len(durations))


def eq12_performance(
    beta: Decimal, mu: Decimal, t: Decimal, g: tuple[Decimal, Decimal, Decimal]
) -> Decimal:
    """Eq. 12 — performance P_i = g1·β_i + g2·μ_i + g3·T_i, g1 + g2 + g3 = 1."""
    g1, g2, g3 = g
    return g1 * _unit(beta, "β") + g2 * _unit(mu, "μ") + g3 * _unit(t, "T")


def apply_change_cap(previous: Decimal, raw: Decimal, cap: Decimal) -> Decimal:
    """DevSync extension (§9.1.2, D86): a parameter moves at most ±cap from its value after the
    previous project. Applied to X, X_m and β only, never to ω, μ or T (counts and ratios)."""
    return max(previous - cap, min(previous + cap, raw))


def platform_mean_beta(betas: Sequence[Decimal], fallback: Decimal) -> Decimal:
    """`rep.newcomer_review` when unset: the mean β of developers with ≥ 3 projects (the caller
    selects them), else `rep.newcomer_review_fallback` (0.6)."""
    if not betas:
        return fallback
    return sum(betas, ZERO) / Decimal(len(betas))


def gamma0(verified_items: int, prm: NewcomerParams) -> Decimal:
    """§9.1.3 (A4): Γ⁰ = min(gamma0_max, gamma0_base + gamma0_per_verification × items).
    Same formula as `newcomer_snapshot()`."""
    if verified_items < 0:
        raise ValueError("verified items must not be negative")
    return min(prm.gamma0_max, prm.gamma0_base + prm.gamma0_per_verification * verified_items)


def omega0(evidence_domains: int) -> Decimal:
    """§9.1.3 (A9): ω⁰ = min(0.5, 0.2 × D), D = domains with passing skill evidence."""
    if evidence_domains < 0:
        raise ValueError("evidence domains must not be negative")
    return min(_OMEGA0_MAX, _OMEGA0_PER_DOMAIN * evidence_domains)


# --------------------------------------------------------------------------- full computation


@dataclass(frozen=True)
class ProjectRecord:
    """One completed project of the developer: the §9.1.1 inputs, normalised to 0–1.

    `internal_slots` are the client's milestone ratings in approval order followed by the
    project-end review, already trust-weighted (§9.14) by the service; `external_slots` are
    verified external reviews for the period (A8). Either may be empty."""

    history_id: str
    domain: str
    client_key: str
    t_days: int
    deadline_days: int
    gamma_comm: Decimal
    gamma_team: Decimal
    internal_slots: tuple[Decimal, ...] = ()
    external_slots: tuple[Decimal, ...] = ()


@dataclass(frozen=True)
class ReputationParams:
    """Every setting the engine uses, built from the active settings by the service (§6.2)."""

    alpha_comm: Decimal = Decimal("0.7")  # rep.alpha_comm, Eq. 2
    alpha_team: Decimal = Decimal("0.7")  # rep.alpha_team, Eq. 3
    kappa_ext: Decimal = Decimal("0.7")  # rep.kappa_ext, Eq. 5
    kappa_int: Decimal = Decimal("0.7")  # rep.kappa_int, Eq. 6
    alpha_x: Decimal = Decimal("0.3")  # rep.alpha_x, Eq. 7
    alpha_e: Decimal = Decimal("0.3")  # rep.alpha_e, Eq. 8
    w_internal: Decimal = Decimal("0.8")  # rep.w_internal, Eq. 9
    w_external: Decimal = Decimal("0.2")  # rep.w_external, Eq. 9
    newcomer: NewcomerParams = field(default_factory=NewcomerParams)  # f, g, Γ⁰, neutral
    newcomer_review: Decimal = Decimal("0.6")  # β with no reviews (resolved by the service)
    max_change: Decimal = Decimal("0.15")  # rep.max_change_per_project
    newcomer_threshold: int = 3  # newcomer.threshold
    mode: Mode = Mode.DEVSYNC  # algorithm.mode

    @property
    def replication(self) -> bool:
        return self.mode is Mode.PCS_REPLICATION


@dataclass(frozen=True)
class Evidence:
    """Newcomer evidence used in devsync mode: verified items (phone, email, complete profile,
    verified certificate) and the domains with passing skill evidence."""

    verified_items: int = 0
    evidence_domains: frozenset[str] = frozenset()


PARAMETERS = ("omega", "x", "xm", "beta", "mu", "t", "c", "p")
CAPPED_PARAMETERS = frozenset({"x", "xm", "beta"})


@dataclass(frozen=True)
class TraceEntry:
    """How one parameter changed after one project (stored in `reputation_log`, shown in "Why did
    this change?"). `raw` is the value before the change cap; equal to `new` when not capped."""

    history_id: str
    parameter: str
    old: Decimal
    raw: Decimal
    new: Decimal
    reason_code: str
    inputs: Mapping[str, str]

    @property
    def capped(self) -> bool:
        return self.raw != self.new


@dataclass(frozen=True)
class SnapshotResult:
    snapshot: Snapshot
    trace: tuple[TraceEntry, ...]
    skill_competency: Mapping[str, Decimal]  # domain → C_{i,s} (devsync only; else empty)


@dataclass
class _State:
    omega: Decimal
    x: Decimal
    xm: Decimal
    beta: Decimal
    mu: Decimal
    t: Decimal


def _start(prm: ReputationParams, ev: Evidence) -> _State:
    """Values before the first project: §9.1.3 in devsync, the paper's zeros in replication."""
    if prm.replication:
        return _State(omega=ZERO, x=ZERO, xm=ZERO, beta=ZERO, mu=ZERO, t=ZERO)
    np_ = prm.newcomer
    return _State(
        omega=omega0(len(ev.evidence_domains)),
        x=gamma0(ev.verified_items, np_),
        xm=np_.neutral,
        beta=prm.newcomer_review,
        mu=np_.neutral,
        t=np_.neutral,
    )


def _s(value: Decimal) -> str:
    return str(_q(value))


@dataclass(frozen=True)
class _ReviewStep:
    lam: Decimal | None
    eps: Decimal | None
    raw: Decimal
    new: Decimal
    code: str
    inputs: dict[str, str]


def _review_step(
    rec: ProjectRecord,
    prm: ReputationParams,
    lam: Decimal | None,
    eps: Decimal | None,
    old_beta: Decimal,
) -> _ReviewStep:
    """Eq. 5–9 for one project: within-project EWMA of the rating slots (Eq. 5, 6), the
    across-project EWMA (Eq. 7, 8; projects without externals are skipped, D87), then β (Eq. 9,
    A8) and, in devsync mode, the change cap. With no internal review yet β keeps its value."""
    inputs: dict[str, str] = {}
    if rec.internal_slots:
        i_n = eq06_internal_within(rec.internal_slots, prm.kappa_int)
        lam = eq07_internal_across(lam, i_n, prm.alpha_x)
        inputs["internal"] = _s(i_n)
    if rec.external_slots:
        e_n = eq05_external_within(rec.external_slots, prm.kappa_ext)
        eps = eq08_external_across(eps, e_n, prm.alpha_e)
        inputs["external"] = _s(e_n)
    if lam is None:
        raw, code = old_beta, "NO_REVIEWS"
    else:
        raw, code = eq09_beta(lam, eps, prm.w_internal, prm.w_external), "REVIEWS"
    new = raw if prm.replication else apply_change_cap(old_beta, raw, prm.max_change)
    return _ReviewStep(lam=lam, eps=eps, raw=raw, new=new, code=code, inputs=inputs)


def compute_snapshot(
    history: Sequence[ProjectRecord],
    params: ReputationParams | None = None,
    evidence: Evidence | None = None,
) -> SnapshotResult:
    """The reputation of one developer from their completed projects, oldest first (§9.1).

    Walks the history one project at a time so every change can be explained: returns the final
    snapshot, one trace entry per parameter per project, and (devsync) per-skill competency.
    With no history in devsync mode the snapshot equals `newcomer_snapshot()`.
    """
    prm = params or ReputationParams()
    ev = evidence or Evidence()
    state = _start(prm, ev)
    lam: Decimal | None = None
    eps: Decimal | None = None
    domains: Counter[str] = Counter()
    clients: Counter[str] = Counter()
    durations: list[tuple[int, int]] = []
    trace: list[TraceEntry] = []
    seen: set[str] = set()
    f, g = prm.newcomer.f, prm.newcomer.g

    for rec in history:
        if rec.history_id in seen:
            raise ValueError(f"duplicate history id {rec.history_id}")
        seen.add(rec.history_id)
        old = _State(**vars(state))
        n = len(durations) + 1

        # Eq. 2–3, then the change cap (ours).
        x_raw = eq02_communication(rec.gamma_comm, old.x, prm.alpha_comm)
        xm_raw = eq03_teamwork(rec.gamma_team, old.xm, prm.alpha_team)
        x_new = x_raw if prm.replication else apply_change_cap(old.x, x_raw, prm.max_change)
        xm_new = xm_raw if prm.replication else apply_change_cap(old.xm, xm_raw, prm.max_change)

        # Eq. 5–9: within the project, across projects, then β (and its cap).
        rv = _review_step(rec, prm, lam, eps, old.beta)
        lam, eps = rv.lam, rv.eps
        beta_raw, beta_new, beta_code, beta_inputs = rv.raw, rv.new, rv.code, rv.inputs

        # Eq. 1, 10, 11 over all projects so far (never capped).
        domains[rec.domain] += 1
        clients[rec.client_key] += 1
        durations.append((rec.t_days, rec.deadline_days))
        if n >= MIN_PROJECTS_FOR_DIVERSITY:
            omega_new, mu_new = eq01_omega(domains), eq10_mu(clients)
        elif prm.replication:
            omega_new, mu_new = ZERO, ZERO
        else:
            omega_new, mu_new = omega0(len(ev.evidence_domains)), prm.newcomer.neutral
        t_new = eq11_timeliness(durations)

        state = _State(omega=omega_new, x=x_new, xm=xm_new, beta=beta_new, mu=mu_new, t=t_new)
        rows: list[tuple[str, Decimal, Decimal, Decimal, str, dict[str, str]]] = [
            ("omega", old.omega, omega_new, omega_new,
             "NEW_DOMAIN" if domains[rec.domain] == 1 else "SAME_DOMAIN",
             {"domain": rec.domain, "projects": str(n), "domains": str(len(domains))}),
            ("x", old.x, x_raw, x_new, "COMMUNICATION", {"rating": _s(rec.gamma_comm)}),
            ("xm", old.xm, xm_raw, xm_new, "TEAMWORK", {"rating": _s(rec.gamma_team)}),
            ("beta", old.beta, beta_raw, beta_new, beta_code, beta_inputs),
            ("mu", old.mu, mu_new, mu_new,
             "RETURNING_CLIENT" if clients[rec.client_key] > 1 else "NEW_CLIENT",
             {"clients": str(len(clients)), "projects": str(n)}),
            ("t", old.t, t_new, t_new,
             "LATE" if rec.t_days > rec.deadline_days else "ON_TIME",
             {"t_days": str(rec.t_days), "deadline_days": str(rec.deadline_days)}),
            ("c", eq04_competency(old.omega, old.x, f), eq04_competency(omega_new, x_new, f),
             eq04_competency(omega_new, x_new, f), "DERIVED", {}),
            ("p", eq12_performance(old.beta, old.mu, old.t, g),
             eq12_performance(beta_new, mu_new, t_new, g),
             eq12_performance(beta_new, mu_new, t_new, g), "DERIVED", {}),
        ]  # fmt: skip
        for name, before, raw, after, code, inputs in rows:
            trace.append(TraceEntry(rec.history_id, name, _q(before), _q(raw), _q(after), code,
                                    inputs))  # fmt: skip

    snapshot = Snapshot(
        omega=_q(state.omega), x=_q(state.x), xm=_q(state.xm), beta=_q(state.beta),
        mu=_q(state.mu), t=_q(state.t),
        c=_q(eq04_competency(state.omega, state.x, f)),
        p=_q(eq12_performance(state.beta, state.mu, state.t, g)),
        completed_projects=len(durations), distinct_clients=len(clients),
    )  # fmt: skip
    skills = {} if prm.replication else skill_competency(domains, ev, state.x, prm)
    return SnapshotResult(snapshot=snapshot, trace=tuple(trace), skill_competency=skills)


_SKILL_EVIDENCE_FLOOR = Decimal("0.2")  # one domain's worth of ω⁰ (§9.1.3)


def skill_competency(
    domain_counts: Mapping[str, int], evidence: Evidence, x: Decimal, params: ReputationParams
) -> dict[str, Decimal]:
    """§9.1.7 per-skill competency C_{i,s} = f·ω_{i,s} + (1 − f)·X_i, per domain (D97).

    ω_{i,s} is the developer's expertise in the slot's domain: the share of their completed
    projects in that domain, n_i^l / N_i; a newcomer (fewer than `newcomer.threshold` projects)
    with passing skill evidence there gets at least 0.2, one domain's worth of ω⁰. Domains with
    neither are left out (ω_{i,s} = 0). Display and the optional `fitness.use_skill_competency`
    only; filtering and fitness use C_i by default."""
    total = sum(domain_counts.values())
    is_newcomer = total < params.newcomer_threshold
    out: dict[str, Decimal] = {}
    for domain in sorted(set(domain_counts) | set(evidence.evidence_domains)):
        share = Decimal(domain_counts.get(domain, 0)) / Decimal(total) if total else ZERO
        if is_newcomer and domain in evidence.evidence_domains:
            share = max(share, _SKILL_EVIDENCE_FLOOR)
        out[domain] = _q(eq04_competency(share, x, params.newcomer.f))
    return out
