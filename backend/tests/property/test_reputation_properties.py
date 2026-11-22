"""Hypothesis properties of the reputation engine (spec §17 Phase 6):
outputs stay in [0, 1]; a higher rating never lowers β; more distinct clients never lower μ;
ω does not depend on project order; the change cap is never exceeded for X, X_m, β and never
applied to ω, μ, T; newcomer values follow §9.1.3 exactly."""

from __future__ import annotations

import random
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.algorithms import reputation as r
from app.algorithms.filtering import Mode

D = Decimal  # short alias for the many decimal literals below
pytestmark = [pytest.mark.property, pytest.mark.unit]

DOMAINS = ["FRONTEND", "BACKEND", "DATABASE", "TESTING", "DESIGN"]
score = st.integers(0, 1000).map(lambda n: D(n) / D(1000))
slots = st.lists(score, min_size=0, max_size=5).map(tuple)


@st.composite
def project(draw: st.DrawFn, idx: int) -> r.ProjectRecord:
    deadline = draw(st.integers(1, 120))
    return r.ProjectRecord(
        history_id=f"p{idx}",
        domain=draw(st.sampled_from(DOMAINS)),
        client_key=draw(st.sampled_from(["a", "b", "c", "d", "e", "f"])),
        t_days=draw(st.integers(0, 2 * deadline)),
        deadline_days=deadline,
        gamma_comm=draw(score),
        gamma_team=draw(score),
        internal_slots=draw(slots),
        external_slots=draw(slots),
    )


@st.composite
def history(draw: st.DrawFn, max_size: int = 12) -> list[r.ProjectRecord]:
    n = draw(st.integers(0, max_size))
    return [draw(project(i)) for i in range(n)]


evidence = st.builds(
    r.Evidence,
    verified_items=st.integers(0, 4),
    evidence_domains=st.frozensets(st.sampled_from(DOMAINS), max_size=5),
)
modes = st.sampled_from([Mode.DEVSYNC, Mode.PCS_REPLICATION])


@settings(max_examples=200, deadline=None)
@given(history(), evidence, modes)
def test_every_output_stays_in_unit_interval(h: list[r.ProjectRecord], ev: r.Evidence,
                                             mode: Mode) -> None:  # fmt: skip
    res = r.compute_snapshot(h, r.ReputationParams(mode=mode), ev)
    s = res.snapshot
    for value in (s.omega, s.x, s.xm, s.beta, s.mu, s.t, s.c, s.p):
        assert D(0) <= value <= D(1)
    for entry in res.trace:
        assert D(0) <= entry.new <= D(1)
    for value in res.skill_competency.values():
        assert D(0) <= value <= D(1)


@settings(max_examples=200, deadline=None)
@given(history(), evidence)
def test_change_cap_holds_for_x_xm_beta_and_never_touches_omega_mu_t(
    h: list[r.ProjectRecord], ev: r.Evidence
) -> None:
    prm = r.ReputationParams()
    for entry in r.compute_snapshot(h, prm, ev).trace:
        if entry.parameter in r.CAPPED_PARAMETERS:
            # Rounded to 3 places: allow one unit of the last place.
            assert abs(entry.new - entry.old) <= prm.max_change + D("0.001")
        elif entry.parameter in {"omega", "mu", "t"}:
            assert entry.new == entry.raw


@settings(max_examples=200, deadline=None)
@given(history(), evidence)
def test_replication_never_caps(h: list[r.ProjectRecord], ev: r.Evidence) -> None:
    res = r.compute_snapshot(h, r.ReputationParams(mode=Mode.PCS_REPLICATION), ev)
    assert all(not e.capped for e in res.trace)


@settings(max_examples=200, deadline=None)
@given(history(8), st.randoms(use_true_random=False))
def test_omega_does_not_depend_on_project_order(
    h: list[r.ProjectRecord], rnd: random.Random
) -> None:
    shuffled = list(h)
    rnd.shuffle(shuffled)
    a = r.compute_snapshot(h).snapshot
    b = r.compute_snapshot(shuffled).snapshot
    assert a.omega == b.omega
    assert a.mu == b.mu  # client diversity is a count too
    assert (a.completed_projects, a.distinct_clients) == (b.completed_projects, b.distinct_clients)


@settings(max_examples=200, deadline=None)
@given(history(), project(99), st.integers(1, 500))
def test_a_higher_rating_never_lowers_beta(
    h: list[r.ProjectRecord], last: r.ProjectRecord, bump: int
) -> None:
    """Raise every internal and external rating of the newest project: β never goes down."""
    if not last.internal_slots:
        last = r.ProjectRecord(**{**vars(last), "internal_slots": (D("0.5"),)})
    better = r.ProjectRecord(**{
        **vars(last),
        "internal_slots": tuple(min(D(1), s + D(bump) / D(1000)) for s in last.internal_slots),
        "external_slots": tuple(min(D(1), s + D(bump) / D(1000)) for s in last.external_slots),
    })  # fmt: skip
    for mode in (Mode.DEVSYNC, Mode.PCS_REPLICATION):
        prm = r.ReputationParams(mode=mode)
        base = r.compute_snapshot([*h, last], prm).snapshot.beta
        assert r.compute_snapshot([*h, better], prm).snapshot.beta >= base


@settings(max_examples=200, deadline=None)
@given(st.lists(st.integers(1, 6), min_size=2, max_size=10))
def test_more_distinct_clients_never_lowers_mu(counts: list[int]) -> None:
    """Moving one hire from a repeat client to a brand-new client never lowers μ."""
    clients = {f"c{i}": n for i, n in enumerate(counts)}
    top = max(clients, key=lambda k: clients[k])
    if clients[top] < 2:  # nothing to move
        return
    spread = dict(clients)
    spread[top] -= 1
    spread["new"] = 1
    assert r.eq10_mu(spread) >= r.eq10_mu(clients)


@settings(max_examples=100, deadline=None)
@given(st.integers(0, 10), st.integers(0, 8), score)
def test_newcomer_values_follow_9_1_3(items: int, domains: int, beta: D) -> None:
    s = r.newcomer_snapshot(r.NewcomerInputs(items, domains, beta))
    assert s.x == min(D("0.60"), D("0.40") + D("0.05") * items).quantize(D("0.001"))
    assert s.omega == min(D("0.5"), D("0.2") * domains).quantize(D("0.001"))
    assert (s.xm, s.mu, s.t) == (D("0.500"),) * 3
    assert s.beta == beta.quantize(D("0.001"))
    ev = r.Evidence(min(items, 4), frozenset(DOMAINS[: min(domains, 5)]))
    computed = r.compute_snapshot([], r.ReputationParams(newcomer_review=beta), ev).snapshot
    assert computed.x <= D("0.600")
    assert computed.completed_projects == 0
