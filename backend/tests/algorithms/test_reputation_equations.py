"""[PCS] Eq. 1–12 by hand (spec §9.1.2, §17 Phase 6). Every test name carries its equation id
(`test_eqNN_…`), which `scripts/check_paper_alignment.py` checks against docs/PAPER_ALIGNMENT.md.
Each fixture's arithmetic is written in its docstring. Defaults: α = α_m = κ = 0.7, α_x = α_e =
0.3, w = 0.8/0.2, f = 0.7, g = (0.5, 0.25, 0.25)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.algorithms import reputation as r

D = Decimal  # short alias for the many decimal literals below
pytestmark = pytest.mark.unit

TOL = D("1e-20")


def close(a: D, b: D | str) -> bool:
    return abs(a - D(b)) < TOL


# ----------------------------------------------------------------------------- Eq. 1


def test_eq01_omega_spec_example_2_1_1() -> None:
    """Domains {FE: 2, BE: 1, DB: 1}, N = 4: Σ n(n−1) = 2·1 = 2; N(N−1) = 12; ω = 1 − 2/12."""
    assert close(r.eq01_omega({"FE": 2, "BE": 1, "DB": 1}), D(1) - D(2) / D(12))
    assert str(r.eq01_omega({"FE": 2, "BE": 1, "DB": 1}))[:6] == "0.8333"


def test_eq01_omega_single_domain_is_zero_and_all_distinct_is_one() -> None:
    """{FE: 4}: 1 − 12/12 = 0. {FE: 1, BE: 1}: 1 − 0/2 = 1. {FE: 3, BE: 1}: 1 − 6/12 = 0.5."""
    assert r.eq01_omega({"FE": 4}) == 0
    assert r.eq01_omega({"FE": 1, "BE": 1}) == 1
    assert r.eq01_omega({"FE": 3, "BE": 1}) == D("0.5")


def test_eq01_omega_refuses_fewer_than_two_projects_and_negative_counts() -> None:
    with pytest.raises(ValueError, match="two projects"):
        r.eq01_omega({"FE": 1})
    with pytest.raises(ValueError, match="two projects"):
        r.eq01_omega({})
    with pytest.raises(ValueError, match="negative"):
        r.eq01_omega({"FE": 3, "BE": -1})


# ----------------------------------------------------------------------------- Eq. 2, 3


def test_eq02_communication_ewma_sequence() -> None:
    """X⁰ = Γ⁰ = 0.5; Γ¹ = 0.9: X¹ = 0.7·0.9 + 0.3·0.5 = 0.78;
    Γ² = 0.6: X² = 0.7·0.6 + 0.3·0.78 = 0.42 + 0.234 = 0.654."""
    x1 = r.eq02_communication(D("0.9"), D("0.5"), D("0.7"))
    assert x1 == D("0.78")
    assert r.eq02_communication(D("0.6"), x1, D("0.7")) == D("0.654")


def test_eq02_communication_boundaries_and_invalid_input() -> None:
    """α = 1 keeps only the newest rating; α = 0 keeps the past. Γ outside [0, 1] is refused."""
    assert r.eq02_communication(D("0.2"), D("0.9"), D(1)) == D("0.2")
    assert r.eq02_communication(D("0.2"), D("0.9"), D(0)) == D("0.9")
    with pytest.raises(ValueError, match="between 0 and 1"):
        r.eq02_communication(D("1.2"), D("0.5"), D("0.7"))
    with pytest.raises(ValueError, match="between 0 and 1"):
        r.eq02_communication(D("0.5"), D("-0.1"), D("0.7"))


def test_eq03_teamwork_ewma_sequence() -> None:
    """X_m⁰ = 0.5; Γ_m¹ = 1: 0.7 + 0.15 = 0.85; Γ_m² = 0: 0 + 0.3·0.85 = 0.255."""
    xm1 = r.eq03_teamwork(D(1), D("0.5"), D("0.7"))
    assert xm1 == D("0.85")
    assert r.eq03_teamwork(D(0), xm1, D("0.7")) == D("0.255")


def test_eq03_teamwork_refuses_out_of_range() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        r.eq03_teamwork(D("1.01"), D("0.5"), D("0.7"))


# ----------------------------------------------------------------------------- Eq. 4


def test_eq04_competency_weights() -> None:
    """ω = 0.5, X = 0.6: 0.7·0.5 + 0.3·0.6 = 0.35 + 0.18 = 0.53.
    ω = 1, X = 0: 0.7. Arif's stage-1 values ω = 0.78, X = 0.86: 0.546 + 0.258 = 0.804."""
    assert r.eq04_competency(D("0.5"), D("0.6"), D("0.7")) == D("0.53")
    assert r.eq04_competency(D(1), D(0), D("0.7")) == D("0.7")
    assert r.eq04_competency(D("0.78"), D("0.86"), D("0.7")) == D("0.804")


def test_eq04_competency_refuses_out_of_range() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        r.eq04_competency(D("1.5"), D("0.6"), D("0.7"))


# ----------------------------------------------------------------------------- Eq. 5, 6


def test_eq05_external_within_project_slots() -> None:
    """κ_e = 0.7. Slots (1.0, 0.5): E¹ = 1; E² = 0.7·0.5 + 0.3·1 = 0.65.
    One slot (0.8): 0.8. Slots (0.5, 1, 1): 0.5 → 0.85 → 0.7 + 0.255 = 0.955."""
    assert r.eq05_external_within((D(1), D("0.5")), D("0.7")) == D("0.65")
    assert r.eq05_external_within((D("0.8"),), D("0.7")) == D("0.8")
    assert r.eq05_external_within((D("0.5"), D(1), D(1)), D("0.7")) == D("0.955")


def test_eq05_external_within_needs_a_rating() -> None:
    with pytest.raises(ValueError, match="at least one"):
        r.eq05_external_within((), D("0.7"))


def test_eq06_internal_within_project_slots() -> None:
    """κ_x = 0.7. Milestone ratings 0.75, 0.5, then the final review 1.0:
    0.75 → 0.7·0.5 + 0.3·0.75 = 0.575 → 0.7·1 + 0.3·0.575 = 0.8725 (recent slots weigh more)."""
    assert r.eq06_internal_within((D("0.75"), D("0.5"), D(1)), D("0.7")) == D("0.8725")


def test_eq06_internal_within_recent_slot_dominates() -> None:
    """(0, 1) → 0.7; (1, 0) → 0.3: κ_x > 0.5 puts more weight on the latest slot."""
    assert r.eq06_internal_within((D(0), D(1)), D("0.7")) == D("0.7")
    assert r.eq06_internal_within((D(1), D(0)), D("0.7")) == D("0.3")
    with pytest.raises(ValueError, match="between 0 and 1"):
        r.eq06_internal_within((D("2"),), D("0.7"))


# ----------------------------------------------------------------------------- Eq. 7, 8


def test_eq07_internal_across_projects() -> None:
    """α_x = 0.3. λ₁ = I₁ = 0.9; I₂ = 0.5: λ₂ = 0.3·0.5 + 0.7·0.9 = 0.15 + 0.63 = 0.78."""
    lam1 = r.eq07_internal_across(None, D("0.9"), D("0.3"))
    assert lam1 == D("0.9")
    assert r.eq07_internal_across(lam1, D("0.5"), D("0.3")) == D("0.78")


def test_eq07_older_projects_weigh_more_with_alpha_x_below_half() -> None:
    """I = (1.0 older, 0.0 newer): λ = 0.3·0 + 0.7·1 = 0.7, closer to the OLDER project (A6)."""
    lam = r.eq07_internal_across(r.eq07_internal_across(None, D(1), D("0.3")), D(0), D("0.3"))
    assert lam == D("0.7")


def test_eq08_external_across_projects() -> None:
    """α_e = 0.3. ε₁ = 0.6; E₂ = 1: ε₂ = 0.3·1 + 0.7·0.6 = 0.72."""
    eps1 = r.eq08_external_across(None, D("0.6"), D("0.3"))
    assert r.eq08_external_across(eps1, D(1), D("0.3")) == D("0.72")


def test_eq08_external_across_refuses_out_of_range() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        r.eq08_external_across(None, D("-0.1"), D("0.3"))


# ----------------------------------------------------------------------------- Eq. 9


def test_eq09_beta_weights_internal_over_external() -> None:
    """λ = 0.8, ε = 0.5: 0.8·0.8 + 0.2·0.5 = 0.64 + 0.10 = 0.74."""
    assert r.eq09_beta(D("0.8"), D("0.5"), D("0.8"), D("0.2")) == D("0.74")


def test_eq09_beta_without_external_reviews_is_lambda() -> None:
    """A8: no verified external reviews → β = λ (not 0.8·λ)."""
    assert r.eq09_beta(D("0.8"), None, D("0.8"), D("0.2")) == D("0.8")


# ----------------------------------------------------------------------------- Eq. 10


def test_eq10_mu_four_different_clients_is_one() -> None:
    """φ = (1, 1, 1, 1), N^r = 4: Σ φ(φ−1) = 0 → μ = 1."""
    assert r.eq10_mu({"a": 1, "b": 1, "c": 1, "d": 1}) == 1


def test_eq10_mu_same_client_four_times_is_zero() -> None:
    """φ = (4), N^r = 4: 1 − 12/12 = 0 (Imran's one-client pattern)."""
    assert r.eq10_mu({"a": 4}) == 0


def test_eq10_mu_mixed_and_invalid() -> None:
    """φ = (2, 2): 1 − (2 + 2)/12 = 0.6667. Fewer than two hires is undefined (A9)."""
    assert str(r.eq10_mu({"a": 2, "b": 2}))[:6] == "0.6666"
    with pytest.raises(ValueError, match="two hires"):
        r.eq10_mu({"a": 1})
    with pytest.raises(ValueError, match="negative"):
        r.eq10_mu({"a": 3, "b": -1})


# ----------------------------------------------------------------------------- Eq. 11


def test_eq11_timeliness_two_projects() -> None:
    """(18 of 30) and (30 of 30): T = 1 − (0.6 + 1.0)/2 = 0.2."""
    assert r.eq11_timeliness([(18, 30), (30, 30)]) == D("0.2")


def test_eq11_timeliness_clip_late_work_contributes_zero() -> None:
    """45 of 30 days: ratio 1.5 clipped to 1 → T = 0 (A2). (15 of 30) and (45 of 30):
    1 − (0.5 + 1)/2 = 0.25."""
    assert r.eq11_timeliness([(45, 30)]) == 0
    assert r.eq11_timeliness([(15, 30), (45, 30)]) == D("0.25")


def test_eq11_timeliness_invalid_input() -> None:
    with pytest.raises(ValueError, match="at least one"):
        r.eq11_timeliness([])
    with pytest.raises(ValueError, match="T\\^d"):
        r.eq11_timeliness([(10, 0)])
    with pytest.raises(ValueError, match="T\\^d"):
        r.eq11_timeliness([(-1, 30)])


# ----------------------------------------------------------------------------- Eq. 12


def test_eq12_performance_default_weights() -> None:
    """β = 0.8, μ = 0.6, T = 0.4: 0.5·0.8 + 0.25·0.6 + 0.25·0.4 = 0.4 + 0.15 + 0.1 = 0.65."""
    g = (D("0.5"), D("0.25"), D("0.25"))
    assert r.eq12_performance(D("0.8"), D("0.6"), D("0.4"), g) == D("0.65")


def test_eq12_performance_other_weights_and_invalid() -> None:
    """g = (1, 0, 0) → P = β. Arif's stage-1 β 0.84, μ 0.80, T 0.70: 0.42 + 0.2 + 0.175 = 0.795."""
    assert r.eq12_performance(D("0.3"), D(1), D(1), (D(1), D(0), D(0))) == D("0.3")
    g = (D("0.5"), D("0.25"), D("0.25"))
    assert r.eq12_performance(D("0.84"), D("0.80"), D("0.70"), g) == D("0.795")
    with pytest.raises(ValueError, match="between 0 and 1"):
        r.eq12_performance(D("1.1"), D(0), D(0), g)


# ----------------------------------------------------------------------------- helpers


def test_change_cap_clamps_both_ways() -> None:
    """cap 0.15 around 0.5: 0.9 → 0.65, 0.1 → 0.35, 0.6 unchanged."""
    assert r.apply_change_cap(D("0.5"), D("0.9"), D("0.15")) == D("0.65")
    assert r.apply_change_cap(D("0.5"), D("0.1"), D("0.15")) == D("0.35")
    assert r.apply_change_cap(D("0.5"), D("0.6"), D("0.15")) == D("0.6")


def test_platform_mean_beta_and_fallback() -> None:
    """mean(0.8, 0.6, 0.7) = 0.7; no experienced developers → the 0.6 fallback."""
    assert r.platform_mean_beta([D("0.8"), D("0.6"), D("0.7")], D("0.6")) == D("0.7")
    assert r.platform_mean_beta([], D("0.6")) == D("0.6")


def test_gamma0_and_omega0_refuse_negative_counts() -> None:
    with pytest.raises(ValueError, match="negative"):
        r.gamma0(-1, r.NewcomerParams())
    with pytest.raises(ValueError, match="negative"):
        r.omega0(-1)
