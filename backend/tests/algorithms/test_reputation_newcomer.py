"""Newcomer starting reputation values (spec §9.1.3). Pure, exact Decimal arithmetic."""

from __future__ import annotations

from decimal import Decimal

from app.algorithms.reputation import NewcomerInputs, newcomer_snapshot


def _inp(verified: int = 2, domains: int = 0, beta: str = "0.6") -> NewcomerInputs:
    return NewcomerInputs(
        verified_items=verified, evidence_domains=domains, newcomer_review_beta=Decimal(beta)
    )


def test_gamma0_grows_with_verified_items_and_caps_at_060() -> None:
    # Γ⁰ = min(0.60, 0.40 + 0.05 × items); X = Γ⁰ (Eq. 2 at n=0).
    assert newcomer_snapshot(_inp(verified=0)).x == Decimal("0.400")
    assert newcomer_snapshot(_inp(verified=2)).x == Decimal("0.500")
    assert newcomer_snapshot(_inp(verified=4)).x == Decimal("0.600")
    assert newcomer_snapshot(_inp(verified=10)).x == Decimal("0.600")  # capped


def test_omega_from_evidence_domains_caps_at_05() -> None:
    assert newcomer_snapshot(_inp(domains=0)).omega == Decimal("0.000")
    assert newcomer_snapshot(_inp(domains=2)).omega == Decimal("0.400")
    assert newcomer_snapshot(_inp(domains=3)).omega == Decimal("0.500")  # min(0.5, 0.6)


def test_neutral_mu_t_and_teamwork() -> None:
    s = newcomer_snapshot(_inp())
    assert s.mu == Decimal("0.500")
    assert s.t == Decimal("0.500")
    assert s.xm == Decimal("0.500")


def test_competency_and_performance_use_default_weights() -> None:
    # verified=4 → X=0.6; domains=3 → ω=0.5; β=0.6.
    s = newcomer_snapshot(_inp(verified=4, domains=3, beta="0.6"))
    # C = 0.7·ω + 0.3·X = 0.7·0.5 + 0.3·0.6 = 0.53.
    assert s.c == Decimal("0.530")
    # P = 0.5·β + 0.25·μ + 0.25·T = 0.5·0.6 + 0.25·0.5 + 0.25·0.5 = 0.55.
    assert s.p == Decimal("0.550")
    assert s.completed_projects == 0
    assert s.distinct_clients == 0


def test_all_scores_within_unit_interval() -> None:
    s = newcomer_snapshot(_inp(verified=4, domains=3, beta="0.9"))
    for value in (s.omega, s.x, s.xm, s.beta, s.mu, s.t, s.c, s.p):
        assert Decimal(0) <= value <= Decimal(1)
