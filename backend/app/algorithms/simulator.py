"""Market simulator (spec §18.3): developers with latent traits and their project histories. PURE.

Deterministic per seed (numpy's PCG64 `Generator`), no clock, no database. Phase 6 uses it to
create the reputation inputs that real reviews and work evidence will provide from Phases 9–11
(DECISIONS D84): `scripts/simulate_market.py` writes JSON for experiments, and the stage-2 demo
seed stores the persona histories as SIMULATED `reputation_history` rows. The latent traits are
the ground truth for experiment E5 ("does reputation track true ability?") and never reach the
application database or the UI.

Model (all draws from one seeded generator, in a fixed order):
- **Developers:** per-domain skill ~ Beta(5, 2) in 1–3 primary domains and Beta(2, 5) elsewhere;
  reliability, teamwork and communication ~ Beta(4, 2); price level ~ U(0.8, 1.3). About
  `newcomer_share` of them are newcomers (0–2 projects); the rest have 3–12.
- **Clients:** budget level ~ U(1.1, 1.4) and rating strictness ~ U(−0.1, 0.1).
- **Projects:** 3–8 milestones on a random DAG (edges only from earlier to later milestones, so
  acyclic by construction; checked with `cpm.compute_cpm`), deadline = CPM duration × U(1.1, 1.4),
  a team of 2–5 whose prices the budget covers after the platform fee.
- **Outcomes:** work span from the developer's milestones stretched by lateness drawn from
  reliability and skill; client ratings (1–5 stars, normalised) from true quality
  q = 0.6·skill + 0.4·reliability, strictness and noise; the §9.1.4 communication rating from
  simulated check-ins, reply times and claims; the §9.1.5 teamwork rating from trust-weighted peer
  ratings (§9.14) and help given; a verified external review on about a quarter of projects.
- **Personas** fix the traits and history shape of named developers (the demo seed, D93).
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from decimal import Decimal

import numpy as np

from app.algorithms.cpm import MilestoneInput, compute_cpm
from app.algorithms.reputation import ProjectRecord
from app.algorithms.trust import Reviewer, reviewer_trust, weighted_mean

DOMAINS = ("FRONTEND", "BACKEND", "DATABASE", "MOBILE", "DESIGN", "TESTING", "DEVOPS", "DATA")
SIM_VERSION = 1  # bump when the model changes; stored with every simulated history
_BASE_DAY_RATE_PAISA = 400_000  # ৳4,000 per working day at price level 1.0
_FEE_BP = 500  # platform fee the budget must cover (pay.platform_fee_bp default)


@dataclass(frozen=True)
class SimParams:
    seed: int = 2026
    developers: int = 200
    clients: int = 40
    newcomer_share: float = 0.30
    external_review_share: float = 0.25
    repeat_client_share: float = 0.30


@dataclass(frozen=True)
class Persona:
    """A named developer with fixed traits and history shape (the demo seed's §18.1 stories)."""

    key: str
    domains: tuple[str, ...]  # primary domains; projects are drawn from these
    projects: int
    clients: int  # distinct clients across those projects (≤ projects)
    skill: float
    reliability: float
    teamwork: float
    communication: float
    price_level: float = 1.0


@dataclass(frozen=True)
class Traits:
    """Latent ground truth (never stored in the app DB)."""

    skill: dict[str, float]
    primary: tuple[str, ...]
    reliability: float
    teamwork: float
    communication: float
    price_level: float

    def quality(self) -> float:
        """True performance ability: 0.6 × mean primary skill + 0.4 × reliability."""
        main = sum(self.skill[d] for d in self.primary) / len(self.primary)
        return 0.6 * main + 0.4 * self.reliability

    def breadth(self) -> float:
        """True expertise and diversity: the domains the developer is skilled in and works in
        (their 1–3 primary domains), on 0–1. This is what ω (Eq. 1) can observe: the spread of
        the domains of their projects. Domains outside the primary ones are only occasional."""
        return len(self.primary) / 3


@dataclass(frozen=True)
class SimProject:
    """One completed project of one developer, in the §9.1.1 input shape (4-place decimals)."""

    key: str
    client_key: str
    domain: str
    milestones: int
    cpm_duration_days: int
    deadline_days: int
    t_days: int
    team_size: int
    budget_paisa: int
    team_prices_paisa: tuple[int, ...]  # the developer's price first
    gamma_comm: str
    gamma_team: str
    internal_slots: tuple[str, ...]
    external_slots: tuple[str, ...]

    def to_record(self) -> ProjectRecord:
        return ProjectRecord(
            history_id=self.key,
            domain=self.domain,
            client_key=self.client_key,
            t_days=self.t_days,
            deadline_days=self.deadline_days,
            gamma_comm=Decimal(self.gamma_comm),
            gamma_team=Decimal(self.gamma_team),
            internal_slots=tuple(Decimal(s) for s in self.internal_slots),
            external_slots=tuple(Decimal(s) for s in self.external_slots),
        )


@dataclass(frozen=True)
class SimDeveloper:
    key: str
    newcomer: bool
    traits: Traits
    history: tuple[SimProject, ...]


@dataclass(frozen=True)
class SimClient:
    key: str
    budget_level: float
    strictness: float
    reviewer: Reviewer = field(compare=False)


@dataclass(frozen=True)
class Market:
    seed: int
    version: int
    clients: tuple[SimClient, ...]
    developers: tuple[SimDeveloper, ...]


# --------------------------------------------------------------------------- helpers


def _d4(x: float) -> str:
    """A 0–1 float as an exact 4-place decimal string (the simulator's only float → Decimal)."""
    return f"{min(1.0, max(0.0, x)):.4f}"


def _stars(rng: np.random.Generator, mean: float) -> str:
    """A 1–5 star rating around `mean` (0–1), normalised r̂ = (r − 1)/4 (spec §9.0)."""
    stars = int(min(5, max(1, round(1 + 4 * (mean + rng.normal(0, 0.08))))))
    return _d4((stars - 1) / 4)


def generate_plan(rng: np.random.Generator) -> tuple[list[MilestoneInput], int]:
    """3–8 milestones; each may depend on earlier ones only (acyclic by construction)."""
    count = int(rng.integers(3, 9))
    milestones = []
    for i in range(count):
        preds = tuple(f"m{j}" for j in range(i) if rng.random() < 0.35)  # noqa: PLR2004
        milestones.append(MilestoneInput(f"m{i}", int(rng.integers(2, 11)), preds))
    return milestones, compute_cpm(milestones).duration


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Spearman's rank correlation with average ranks for ties (E5, §9.18)."""
    if len(xs) != len(ys) or len(xs) < 2:  # noqa: PLR2004
        raise ValueError("need two equally long series of at least two values")

    def ranks(values: Sequence[float]) -> np.ndarray:
        arr = np.asarray(values, dtype=float)
        order = np.argsort(arr, kind="stable")
        out = np.empty(len(arr))
        i = 0
        while i < len(arr):
            j = i
            while j + 1 < len(arr) and arr[order[j + 1]] == arr[order[i]]:
                j += 1
            out[order[i : j + 1]] = (i + j) / 2
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    if rx.std() == 0 or ry.std() == 0:
        raise ValueError("a constant series has no rank correlation")
    return float(np.corrcoef(rx, ry)[0, 1])


# --------------------------------------------------------------------------- generation


def _random_traits(rng: np.random.Generator) -> Traits:
    primary_count = int(rng.integers(1, 4))
    primary = tuple(str(d) for d in rng.choice(DOMAINS, size=primary_count, replace=False))
    skill = {d: float(rng.beta(5, 2) if d in primary else rng.beta(2, 5)) for d in DOMAINS}
    return Traits(
        skill=skill,
        primary=primary,
        reliability=float(rng.beta(4, 2)),
        teamwork=float(rng.beta(4, 2)),
        communication=float(rng.beta(4, 2)),
        price_level=float(rng.uniform(0.8, 1.3)),
    )


def _persona_traits(p: Persona) -> Traits:
    skill = {d: (p.skill if d in p.domains else 0.3) for d in DOMAINS}
    return Traits(skill, p.domains, p.reliability, p.teamwork, p.communication, p.price_level)


def _client(rng: np.random.Generator, idx: int) -> SimClient:
    reviewer = Reviewer(
        age_days=int(rng.integers(30, 720)),
        completed=int(rng.integers(0, 12)),
        verified=bool(rng.random() < 0.8),  # noqa: PLR2004
        consistency_history=Decimal(_d4(float(rng.beta(6, 2)))),
    )
    return SimClient(
        key=f"client-{idx:03d}",
        budget_level=float(rng.uniform(1.1, 1.4)),
        strictness=float(rng.uniform(-0.1, 0.1)),
        reviewer=reviewer,
    )


def _gamma_comm(rng: np.random.Generator, comm: float, client: SimClient, weeks: int) -> float:
    """§9.1.4: Γ = 0.6·E_comm + 0.4·R_comm from simulated check-ins, replies and claims."""
    on_time = int(rng.binomial(weeks, comm)) / weeks
    reply_hours = max(0.0, 72 * (1 - comm) + float(rng.normal(0, 6)))
    reply = 1.0 if reply_hours <= 24 else max(0.0, (72 - reply_hours) / 48)  # noqa: PLR2004
    claims = min(1.0, max(0.0, comm + float(rng.normal(0, 0.1))))
    e_comm = 0.5 * on_time + 0.3 * reply + 0.2 * claims
    r_comm = float(_stars(rng, comm + client.strictness))
    return 0.6 * e_comm + 0.4 * r_comm


def _gamma_team(rng: np.random.Generator, teamwork: float, peers: int) -> float:
    """§9.1.5: Γ_m = 0.8·peer + 0.2·help; peer = trust-weighted mean of peer ratings (§9.14)."""
    ratings, weights = [], []
    for _ in range(peers):
        ratings.append(Decimal(_stars(rng, teamwork)))
        peer = Reviewer(
            age_days=int(rng.integers(14, 900)),
            completed=int(rng.integers(0, 10)),
            verified=bool(rng.random() < 0.7),  # noqa: PLR2004
            consistency_history=Decimal(_d4(float(rng.beta(5, 2)))),
        )
        weights.append(reviewer_trust(peer))
    mean = weighted_mean(ratings, weights)
    peer_score = float(mean) if mean is not None else 0.5
    helped = int(rng.poisson(8 * teamwork * 0.8))
    return 0.8 * peer_score + 0.2 * min(1.0, helped / 8)


def _project(
    rng: np.random.Generator,
    *,
    key: str,
    traits: Traits,
    domain: str,
    client: SimClient,
    params: SimParams,
) -> SimProject:
    milestones, cpm_days = generate_plan(rng)
    deadline = max(1, math.ceil(cpm_days * float(rng.uniform(1.1, 1.4))))
    skill = traits.skill[domain]
    # Lateness: reliable, skilled people finish inside their planned span; others stretch it.
    planned = max(1, round(cpm_days * float(rng.uniform(0.7, 1.0))))
    stretch = math.exp(
        float(rng.normal((0.55 - traits.reliability) * 1.5 + (0.55 - skill) * 0.3, 0.15))
    )
    t_days = max(1, round(planned * stretch))
    team_size = int(rng.integers(2, 6))
    own_price = round(_BASE_DAY_RATE_PAISA * traits.price_level * planned / 10_000) * 10_000
    others = [
        round(_BASE_DAY_RATE_PAISA * float(rng.uniform(0.8, 1.3)) * planned / 10_000) * 10_000
        for _ in range(team_size - 1)
    ]
    prices = (own_price, *others)
    # The budget after the platform fee covers the team, with the client's margin on top.
    budget = math.ceil(sum(prices) * client.budget_level * 10_000 / (10_000 - _FEE_BP))
    budget = math.ceil(budget / 10_000) * 10_000
    q = 0.6 * skill + 0.4 * traits.reliability
    ratings = len(milestones) // 2 + 1  # milestone ratings, then the project-end review
    internal = tuple(_stars(rng, q + client.strictness) for _ in range(ratings))
    external = (_stars(rng, q),) if rng.random() < params.external_review_share else ()
    weeks = max(1, math.ceil(t_days / 7))
    return SimProject(
        key=key,
        client_key=client.key,
        domain=domain,
        milestones=len(milestones),
        cpm_duration_days=cpm_days,
        deadline_days=deadline,
        t_days=t_days,
        team_size=team_size,
        budget_paisa=budget,
        team_prices_paisa=prices,
        gamma_comm=_d4(_gamma_comm(rng, traits.communication, client, weeks)),
        gamma_team=_d4(_gamma_team(rng, traits.teamwork, team_size - 1)),
        internal_slots=internal,
        external_slots=external,
    )


def _client_sequence(
    rng: np.random.Generator, clients: Sequence[SimClient], projects: int, distinct: int | None,
    repeat_share: float,
) -> list[SimClient]:  # fmt: skip
    """Which client hired the developer for each project. Personas fix the distinct count."""
    if distinct is not None:
        if not 1 <= distinct <= projects:
            raise ValueError("a persona needs 1 ≤ clients ≤ projects")
        chosen = [clients[int(i)] for i in rng.choice(len(clients), size=distinct, replace=False)]
        extra = [chosen[int(rng.integers(0, distinct))] for _ in range(projects - distinct)]
        order = chosen + extra
        return [order[int(i)] for i in rng.permutation(projects)]
    seq: list[SimClient] = []
    for _ in range(projects):
        if seq and rng.random() < repeat_share:
            seq.append(seq[int(rng.integers(0, len(seq)))])
        else:
            seq.append(clients[int(rng.integers(0, len(clients)))])
    return seq


def _developer(
    rng: np.random.Generator,
    *,
    key: str,
    traits: Traits,
    projects: int,
    distinct_clients: int | None,
    clients: Sequence[SimClient],
    params: SimParams,
    newcomer_threshold: int,
) -> SimDeveloper:
    sequence = _client_sequence(rng, clients, projects, distinct_clients,
                                params.repeat_client_share)  # fmt: skip
    history = []
    for n, client in enumerate(sequence):
        in_primary = rng.random() < 0.85  # noqa: PLR2004
        domain = str(rng.choice(traits.primary if in_primary else DOMAINS))
        history.append(_project(rng, key=f"{key}-p{n + 1:02d}", traits=traits, domain=domain,
                                client=client, params=params))  # fmt: skip
    return SimDeveloper(key, projects < newcomer_threshold, traits, tuple(history))


def simulate_market(
    params: SimParams | None = None,
    personas: Sequence[Persona] = (),
    newcomer_threshold: int = 3,
) -> Market:
    """Generate clients, random developers and the given personas with their histories."""
    prm = params or SimParams()
    if prm.developers < 0 or prm.clients < 1:
        raise ValueError("need ≥ 0 developers and ≥ 1 client")
    if not 0 <= prm.newcomer_share <= 1:
        raise ValueError("newcomer_share must be between 0 and 1")
    rng = np.random.default_rng(prm.seed)
    clients = tuple(_client(rng, i) for i in range(prm.clients))
    developers = []
    for p in personas:
        if p.projects < 0 or any(d not in DOMAINS for d in p.domains) or not p.domains:
            raise ValueError(f"invalid persona {p.key}")
        distinct = p.clients if p.projects else None
        developers.append(_developer(rng, key=p.key, traits=_persona_traits(p),
                                     projects=p.projects, distinct_clients=distinct,
                                     clients=clients, params=prm,
                                     newcomer_threshold=newcomer_threshold))  # fmt: skip
    for i in range(prm.developers):
        traits = _random_traits(rng)
        newcomer = rng.random() < prm.newcomer_share
        projects = int(rng.integers(0, newcomer_threshold) if newcomer else rng.integers(3, 13))
        developers.append(_developer(rng, key=f"dev-{i:04d}", traits=traits, projects=projects,
                                     distinct_clients=None, clients=clients, params=prm,
                                     newcomer_threshold=newcomer_threshold))  # fmt: skip
    return Market(prm.seed, SIM_VERSION, clients, tuple(developers))


def market_to_json(market: Market) -> str:
    """Canonical JSON (sorted keys, fixed separators): same seed → byte-identical output."""
    data = asdict(market)
    for client in data["clients"]:
        client["reviewer"]["consistency_history"] = str(client["reviewer"]["consistency_history"])
    return json.dumps(data, sort_keys=True, separators=(",", ":"))
