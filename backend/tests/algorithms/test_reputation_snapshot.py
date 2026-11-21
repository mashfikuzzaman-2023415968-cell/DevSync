"""`compute_snapshot()` over whole histories, the ambiguity resolutions A1, A2, A4, A5, A6, A8,
A9 (spec §9.0; A3, A7, A10–A13 are tested with the code they belong to, DECISIONS D91), every
`pcs_replication` switch, and settings validation (§9.1.2 "validate weight ranges on save").

The worked example below is the one in docs/ALGORITHMS.md.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.algorithms import reputation as r
from app.algorithms.filtering import Mode
from app.schemas.platform_settings import RepSettings

D = Decimal  # short alias for the many decimal literals below
pytestmark = pytest.mark.unit

REPLICATION = r.ReputationParams(mode=Mode.PCS_REPLICATION)

# Worked example: a newcomer with 3 verified items (Γ⁰ = 0.55) and passing evidence in one
# domain (ω⁰ = 0.2); β with no reviews = 0.6.
EVIDENCE = r.Evidence(verified_items=3, evidence_domains=frozenset({"FRONTEND"}))
PROJECT_A = r.ProjectRecord(
    history_id="A", domain="FRONTEND", client_key="c1", t_days=20, deadline_days=30,
    gamma_comm=D("0.8"), gamma_team=D("0.7"), internal_slots=(D("0.75"), D(1)),
)  # fmt: skip
PROJECT_B = r.ProjectRecord(
    history_id="B", domain="BACKEND", client_key="c2", t_days=33, deadline_days=30,
    gamma_comm=D("0.6"), gamma_team=D("0.9"), internal_slots=(D("0.5"),),
    external_slots=(D(1),),
)  # fmt: skip


def _trace(result: r.SnapshotResult, history_id: str, parameter: str) -> r.TraceEntry:
    return next(e for e in result.trace if e.history_id == history_id and e.parameter == parameter)


def test_worked_example_two_projects() -> None:
    """Project A (FRONTEND, client c1, 20 of 30 days, Γ 0.8, Γ_m 0.7, ratings 0.75 then 1.0):
      X = 0.7·0.8 + 0.3·0.55 = 0.725 → capped at 0.55 + 0.15 = 0.700
      X_m = 0.7·0.7 + 0.3·0.5 = 0.640;  I = 0.7·1 + 0.3·0.75 = 0.925 = λ = β_raw → capped 0.750
      ω = ω⁰ = 0.2 (one project); μ = 0.5; T = 1 − 20/30 = 0.333
    Project B (BACKEND, client c2, 33 of 30 days, Γ 0.6, Γ_m 0.9, rating 0.5, external 1.0):
      X = 0.7·0.6 + 0.3·0.70 = 0.630;  X_m = 0.7·0.9 + 0.3·0.64 = 0.822 → capped at 0.790
      λ = 0.3·0.5 + 0.7·0.925 = 0.7975;  ε = 1.0;  β = 0.8·0.7975 + 0.2·1 = 0.838
      ω = 1 − 0/2 = 1;  μ = 1;  T = 1 − (20/30 + min(33/30, 1))/2 = 0.1667
      C = 0.7·1 + 0.3·0.63 = 0.889;  P = 0.5·0.838 + 0.25·1 + 0.25·0.1667 = 0.7107
    """
    res = r.compute_snapshot([PROJECT_A, PROJECT_B], evidence=EVIDENCE)
    s = res.snapshot
    assert (s.omega, s.x, s.xm, s.beta, s.mu, s.t) == (
        D("1.000"), D("0.630"), D("0.790"), D("0.838"), D("1.000"), D("0.167"),
    )  # fmt: skip
    assert (s.c, s.p) == (D("0.889"), D("0.711"))
    assert (s.completed_projects, s.distinct_clients) == (2, 2)
    x_a = _trace(res, "A", "x")
    assert (x_a.old, x_a.raw, x_a.new, x_a.capped) == (D("0.550"), D("0.725"), D("0.700"), True)
    beta_a = _trace(res, "A", "beta")
    assert (beta_a.raw, beta_a.new, beta_a.reason_code) == (D("0.925"), D("0.750"), "REVIEWS")
    assert _trace(res, "B", "t").reason_code == "LATE"
    assert _trace(res, "A", "mu").reason_code == "NEW_CLIENT"
    assert _trace(res, "B", "omega").reason_code == "NEW_DOMAIN"
    # Every parameter is traced for every project.
    assert len(res.trace) == 2 * len(r.PARAMETERS)


def test_worked_example_skill_competency() -> None:
    """Still a newcomer (2 < 3 projects). FRONTEND share 1/2 (≥ the 0.2 evidence floor) and
    BACKEND 1/2: C_s = 0.7·0.5 + 0.3·0.63 = 0.539 each."""
    res = r.compute_snapshot([PROJECT_A, PROJECT_B], evidence=EVIDENCE)
    assert res.skill_competency == {"BACKEND": D("0.539"), "FRONTEND": D("0.539")}


def test_skill_competency_evidence_floor_only_for_newcomers() -> None:
    """With 3 projects (not a newcomer) evidence no longer lifts a domain: 3 FRONTEND projects
    and evidence in DATA → DATA ω_s = 0, so C_s = 0.3·X."""
    hist = [
        r.ProjectRecord(str(i), "FRONTEND", f"c{i}", 10, 30, D("0.6"), D("0.6")) for i in range(3)
    ]
    ev = r.Evidence(verified_items=4, evidence_domains=frozenset({"DATA"}))
    res = r.compute_snapshot(hist, evidence=ev)
    x = res.snapshot.x
    assert res.skill_competency["DATA"] == (D("0.3") * x).quantize(D("0.001"))
    assert res.skill_competency["FRONTEND"] == (D("0.7") + D("0.3") * x).quantize(D("0.001"))


def test_empty_history_equals_newcomer_snapshot() -> None:
    """No projects in devsync mode = the §9.1.3 starting values."""
    for items, domains in ((0, set()), (2, {"FRONTEND"}), (4, {"FRONTEND", "BACKEND", "DATA"})):
        res = r.compute_snapshot([], evidence=r.Evidence(items, frozenset(domains)))
        expected = r.newcomer_snapshot(r.NewcomerInputs(items, len(domains), D("0.6")))
        assert res.snapshot == expected
        assert res.trace == ()


def test_duplicate_history_ids_are_refused() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        r.compute_snapshot([PROJECT_A, PROJECT_A])


def test_invalid_project_input_is_refused() -> None:
    bad = r.ProjectRecord("X", "FRONTEND", "c", 10, 30, D("1.2"), D("0.5"))
    with pytest.raises(ValueError, match="between 0 and 1"):
        r.compute_snapshot([bad])
    with pytest.raises(ValueError, match="T\\^d"):
        r.compute_snapshot([r.ProjectRecord("Y", "FRONTEND", "c", 10, 0, D("0.5"), D("0.5"))])


def test_no_reviews_keeps_beta_at_newcomer_review() -> None:
    """A project without client ratings leaves β at rep.newcomer_review (§9.1.2 rule)."""
    rec = r.ProjectRecord("A", "FRONTEND", "c", 10, 30, D("0.5"), D("0.5"))
    res = r.compute_snapshot([rec], r.ReputationParams(newcomer_review=D("0.65")))
    assert res.snapshot.beta == D("0.650")
    assert _trace(res, "A", "beta").reason_code == "NO_REVIEWS"


# ----------------------------------------------------------------------------- A1–A9


def test_A1_timeliness_direction() -> None:  # noqa: N802 — name required by spec §9.0
    """A1: Eq. 11 as written — faster work gives a HIGHER T (10 of 30 → 0.667; 25 of 30 → 0.167),
    so T rewards punctuality like every other reputation parameter."""
    fast = r.eq11_timeliness([(10, 30)])
    slow = r.eq11_timeliness([(25, 30)])
    assert fast > slow
    assert str(fast)[:5] == "0.666"


def test_A2_late_work_is_clipped() -> None:  # noqa: N802 — name required by spec §9.0
    """A2: 45 of 30 days → 0 with the clip (default); the unclipped alternative gives −0.5, which
    would leave [0, 1]. Replication keeps the clip (it is unavoidable)."""
    assert r.eq11_timeliness([(45, 30)]) == 0
    assert r.eq11_timeliness([(45, 30)], clip=False) == D("-0.5")
    late = r.ProjectRecord("L", "FRONTEND", "c", 45, 30, D("0.5"), D("0.5"))
    assert r.compute_snapshot([late], REPLICATION).snapshot.t == D("0.000")


def test_A4_initial_communication_from_verification() -> None:  # noqa: N802 — name required by spec §9.0
    """A4: Γ⁰ = min(0.6, 0.4 + 0.05 × verified items) → 4 items give X = 0.6; the paper's
    alternative ("set to zero") is what pcs_replication uses: X = 0."""
    ev = r.Evidence(verified_items=4)
    assert r.compute_snapshot([], evidence=ev).snapshot.x == D("0.600")
    assert r.compute_snapshot([], REPLICATION, ev).snapshot.x == D("0.000")


def test_A5_competency_weights_sum_to_one() -> None:  # noqa: N802 — name required by spec §9.0
    """A5: "ω + X = 1" read as the weights f and 1 − f summing to 1, so ω = X = v gives C = v
    for any f (the alternative, ω + X = 1 as values, would constrain the data instead)."""
    for f in (D(0), D("0.3"), D("0.7"), D(1)):
        assert r.eq04_competency(D("0.42"), D("0.42"), f) == D("0.42")


def test_A6_older_projects_weigh_more() -> None:  # noqa: N802 — name required by spec §9.0
    """A6: α_x = 0.3 (< 0.5) puts 0.7 on the older history: ratings 1.0 then 0.0 give λ = 0.7.
    The alternative α_x = 0.7 would give 0.3, and settings refuse α_x ≥ 0.5."""
    first = r.eq07_internal_across(None, D(1), D("0.3"))
    older_first = r.eq07_internal_across(first, D(0), D("0.3"))
    assert older_first == D("0.7")
    first_alt = r.eq07_internal_across(None, D(1), D("0.7"))
    newer_heavy = r.eq07_internal_across(first_alt, D(0), D("0.7"))
    assert newer_heavy == D("0.3")
    with pytest.raises(ValidationError):
        RepSettings(alpha_x=D("0.7"))


def test_A8_beta_uses_internal_reviews_only_without_verified_externals() -> None:  # noqa: N802 — name required by spec §9.0
    """A8: no verified external reviews → β = λ = 0.925 (capped to 0.75 for a newcomer);
    replication (no cap) shows the raw 0.925. With an external 0.5: 0.8·0.925 + 0.2·0.5 = 0.84."""
    assert r.compute_snapshot([PROJECT_A], REPLICATION).snapshot.beta == D("0.925")
    with_ext = r.ProjectRecord(
        "E", "FRONTEND", "c1", 20, 30, D("0.8"), D("0.7"), (D("0.75"), D(1)), (D("0.5"),)
    )
    assert r.compute_snapshot([with_ext], REPLICATION).snapshot.beta == D("0.840")


def test_A9_omega_and_mu_below_two_projects() -> None:  # noqa: N802 — name required by spec §9.0
    """A9: with one project ω comes from skill evidence (2 domains → 0.4; none → 0) and μ is the
    neutral 0.5; from two projects Eq. 1/10 take over. Replication uses 0 below two projects."""
    one = [PROJECT_A]
    two_domains = r.Evidence(1, frozenset({"FRONTEND", "DATA"}))
    assert r.compute_snapshot(one, evidence=two_domains).snapshot.omega == D("0.400")
    assert r.compute_snapshot(one, evidence=r.Evidence()).snapshot.omega == D("0.000")
    assert r.compute_snapshot(one, evidence=two_domains).snapshot.mu == D("0.500")
    rep = r.compute_snapshot(one, REPLICATION, two_domains).snapshot
    assert (rep.omega, rep.mu) == (D("0.000"), D("0.000"))


# ----------------------------------------------------------------------------- pcs_replication


def test_replication_switches_off_the_change_cap() -> None:
    """Same history: devsync caps X at 0.700 after project A, replication keeps 0.56
    (0.7·0.8 + 0.3·0, starting from 0)."""
    dev = _trace(r.compute_snapshot([PROJECT_A], evidence=EVIDENCE), "A", "x")
    rep = _trace(r.compute_snapshot([PROJECT_A], REPLICATION, EVIDENCE), "A", "x")
    assert dev.capped
    assert dev.new == D("0.700")
    assert not rep.capped
    assert rep.new == D("0.560")


def test_replication_switches_off_newcomer_starting_values() -> None:
    """Replication starts from the paper's zeros whatever the evidence."""
    s = r.compute_snapshot([], REPLICATION, r.Evidence(4, frozenset({"FRONTEND"}))).snapshot
    assert (s.omega, s.x, s.xm, s.beta, s.mu, s.t, s.c, s.p) == (D("0.000"),) * 8


def test_replication_switches_off_skill_competency() -> None:
    assert r.compute_snapshot([PROJECT_A, PROJECT_B], REPLICATION, EVIDENCE).skill_competency == {}


def test_replication_full_example() -> None:
    """Replication on the worked example: X 0.56 → 0.42 + 0.168 = 0.588; X_m 0.49 → 0.777;
    β = 0.838; ω = μ = 1; T = 0.167; C = 0.7 + 0.3·0.588 = 0.876; P = 0.711."""
    s = r.compute_snapshot([PROJECT_A, PROJECT_B], REPLICATION, EVIDENCE).snapshot
    assert (s.x, s.xm, s.beta, s.c, s.p) == (
        D("0.588"), D("0.777"), D("0.838"), D("0.876"), D("0.711"),
    )  # fmt: skip


# ----------------------------------------------------------------------------- settings


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kappa_ext", "0.5"),
        ("kappa_int", "0.4"),
        ("alpha_x", "0.5"),
        ("alpha_e", "0.6"),
        ("max_change_per_project", "0"),
    ],
)
def test_settings_refuse_out_of_range_weights(field: str, value: str) -> None:
    """κ must be > 0.5, α_x and α_e < 0.5 (§9.1.2), and the cap positive."""
    with pytest.raises(ValidationError):
        RepSettings(**{field: D(value)})


def test_settings_refuse_weights_not_summing_to_one() -> None:
    with pytest.raises(ValidationError, match="w_internal"):
        RepSettings(w_internal=D("0.7"), w_external=D("0.2"))
    with pytest.raises(ValidationError, match="sum to 1"):
        RepSettings(g=(D("0.5"), D("0.3"), D("0.3")))


def test_settings_accept_the_boundaries_just_inside() -> None:
    RepSettings(kappa_ext=D("0.51"), kappa_int=D("1"), alpha_x=D("0.49"), alpha_e=D("0"))
