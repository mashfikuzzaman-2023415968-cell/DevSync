"""Market simulator (spec §18.3) and the E5 check (§19, DECISIONS D96).

Determinism, ranges, acyclic plans, budgets that cover the team, personas, Spearman by hand, and
"does reputation track true ability?" on simulated histories."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from app.algorithms import reputation as r
from app.algorithms import simulator as s
from app.algorithms.cpm import compute_cpm

pytestmark = pytest.mark.unit

SEED_DATA = Path(__file__).resolve().parents[2] / "scripts" / "seed_data"
PERSONAS_FILE = SEED_DATA / "stage2_personas.json"


@pytest.fixture(scope="module")
def market() -> s.Market:
    return s.simulate_market()


def test_same_seed_gives_byte_identical_output() -> None:
    a = s.market_to_json(s.simulate_market(s.SimParams(seed=11, developers=40)))
    b = s.market_to_json(s.simulate_market(s.SimParams(seed=11, developers=40)))
    assert a == b
    json.loads(a)  # valid JSON


def test_different_seeds_give_different_output() -> None:
    a = s.market_to_json(s.simulate_market(s.SimParams(seed=11, developers=40)))
    b = s.market_to_json(s.simulate_market(s.SimParams(seed=12, developers=40)))
    assert a != b


def test_traits_and_newcomer_share_in_range(market: s.Market) -> None:
    """~30% newcomers (0–2 projects), the rest 3–12; traits on 0–1; price level 0.8–1.3."""
    devs = market.developers
    share = sum(d.newcomer for d in devs) / len(devs)
    assert 0.2 <= share <= 0.4
    for d in devs:
        n = len(d.history)
        assert (n < 3) if d.newcomer else (3 <= n <= 12)
        t = d.traits
        assert all(0 <= v <= 1 for v in (*t.skill.values(), t.reliability, t.teamwork,
                                          t.communication))  # fmt: skip
        assert 0.8 <= t.price_level <= 1.3
        assert 1 <= len(t.primary) <= 3


def test_every_generated_plan_is_acyclic() -> None:
    """500 plans: compute_cpm accepts each (it raises on a cycle) and 3–8 milestones."""
    rng = np.random.default_rng(5)
    for _ in range(500):
        milestones, duration = s.generate_plan(rng)
        assert 3 <= len(milestones) <= 8
        assert compute_cpm(milestones).duration == duration


def test_projects_are_consistent(market: s.Market) -> None:
    """Deadline ≥ CPM duration; budget after the 5% fee covers the team; inputs on 0–1."""
    for d in market.developers:
        for p in d.history:
            assert p.deadline_days >= p.cpm_duration_days >= 2
            assert p.t_days >= 1
            assert len(p.team_prices_paisa) == p.team_size
            assert p.budget_paisa * 95 // 100 >= sum(p.team_prices_paisa)
            assert all(isinstance(x, int) and x > 0 for x in p.team_prices_paisa)
            values = [p.gamma_comm, p.gamma_team, *p.internal_slots, *p.external_slots]
            assert all(Decimal(0) <= Decimal(v) <= 1 for v in values)
            assert p.internal_slots  # every completed project has client ratings


def test_ground_truth_is_not_part_of_the_records(market: s.Market) -> None:
    """What reaches the engine (and the DB) is the §9.1.1 input only, never latent traits."""
    record = market.developers[0].history[0].to_record() if market.developers[0].history else None
    for d in market.developers:
        if d.history:
            record = d.history[0].to_record()
            break
    assert record is not None
    assert not {"skill", "reliability", "teamwork", "communication"} & set(vars(record))


def test_personas_keep_their_shape() -> None:
    p = s.Persona("imran", ("TESTING", "DEVOPS"), projects=7, clients=1, skill=0.85,
                  reliability=0.8, teamwork=0.6, communication=0.7)  # fmt: skip
    q = s.Persona("arif", ("FRONTEND",), projects=8, clients=5, skill=0.8, reliability=0.8,
                  teamwork=0.8, communication=0.8)  # fmt: skip
    m = s.simulate_market(s.SimParams(developers=0), [p, q])
    imran, arif = m.developers
    assert len(imran.history) == 7
    assert len({h.client_key for h in imran.history}) == 1
    assert len({h.client_key for h in arif.history}) == 5
    assert not imran.newcomer


@pytest.mark.parametrize(
    ("domains", "projects", "clients"),
    [((), 3, 1), (("NOPE",), 3, 1), (("FRONTEND",), 2, 3), (("FRONTEND",), -1, 1)],
)
def test_invalid_personas_are_refused(domains: tuple[str, ...], projects: int,
                                      clients: int) -> None:  # fmt: skip
    p = s.Persona("x", domains, projects, clients, 0.5, 0.5, 0.5, 0.5)
    with pytest.raises(ValueError, match="persona"):
        s.simulate_market(s.SimParams(developers=0), [p])


def test_invalid_params_are_refused() -> None:
    with pytest.raises(ValueError, match="client"):
        s.simulate_market(s.SimParams(clients=0))
    with pytest.raises(ValueError, match="newcomer_share"):
        s.simulate_market(s.SimParams(newcomer_share=1.5))


def test_spearman_by_hand() -> None:
    """Same order → 1; reversed → −1; x = (1, 2, 3, 4), y = (1, 3, 2, 4): d² = 0+1+1+0 = 2,
    rho = 1 − 6·2/(4·15) = 0.8. Ties get average ranks."""
    assert s.spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1)
    assert s.spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1)
    assert s.spearman([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(0.8)
    assert s.spearman([1, 1, 2], [1, 1, 2]) == pytest.approx(1)


def test_spearman_refuses_bad_input() -> None:
    with pytest.raises(ValueError, match="equally long"):
        s.spearman([1, 2], [1])
    with pytest.raises(ValueError, match="equally long"):
        s.spearman([1], [1])
    with pytest.raises(ValueError, match="constant"):
        s.spearman([1, 1, 1], [1, 2, 3])


def test_E5_reputation_tracks_true_ability(market: s.Market) -> None:  # noqa: N802 — E5 (§19)
    """E5 (D96): over experienced simulated developers (≥ 3 projects, seed 2026), Spearman rho
    between computed P and latent quality, and between computed C and latent breadth +
    communication, must each be ≥ 0.5. Measured (recorded in docs/ALGORITHMS.md): 0.797, 0.759."""
    experienced = [d for d in market.developers if len(d.history) >= 3]
    assert len(experienced) >= 100
    snaps = [r.compute_snapshot([p.to_record() for p in d.history]).snapshot for d in experienced]
    rho_p = s.spearman([float(x.p) for x in snaps], [d.traits.quality() for d in experienced])
    latent_c = [0.7 * d.traits.breadth() + 0.3 * d.traits.communication for d in experienced]
    rho_c = s.spearman([float(x.c) for x in snaps], latent_c)
    assert rho_p >= 0.5
    assert rho_c >= 0.5
    assert round(rho_p, 3) == 0.797  # deterministic for this seed
    assert round(rho_c, 3) == 0.759


def test_stage2_personas_keep_every_bidder_eligible() -> None:
    """The seeded personas' computed reputations pass Algorithm 1's defaults (P ≥ 0.45,
    C ≥ 0.40) for every experienced bidder on the ordering system, and keep the §18.1 stories."""
    data = json.loads(PERSONAS_FILE.read_text(encoding="utf-8"))
    personas = [s.Persona(**{**p, "domains": tuple(p["domains"])}) for p in data["personas"]]
    m = s.simulate_market(s.SimParams(seed=data["seed"], developers=0, clients=data["clients"]),
                          personas)  # fmt: skip
    ev = r.Evidence(3)
    snaps = {
        d.key: r.compute_snapshot([p.to_record() for p in d.history], evidence=ev).snapshot
        for d in m.developers
    }
    bidders = ["arif", "nusrat", "tanvir", "farhan", "sadia", "rafi", "zahid", "imran", "shakib"]
    for key in bidders:
        assert snaps[key].p >= Decimal("0.45"), key
        assert snaps[key].c >= Decimal("0.40"), key
    assert snaps["imran"].mu == 0  # 7 projects, one client (R1 pattern)
    assert snaps["arif"].completed_projects == 8
    assert snaps["arif"].distinct_clients == 5
    assert snaps["shakib"].t == min(x.t for x in snaps.values())  # often late
    assert snaps["rafsan"].completed_projects == 1  # "Newcomer · 1 of 3 projects done"
