# Market simulator

Spec §18.3; code `backend/app/algorithms/simulator.py` (pure, seeded), CLI
`backend/scripts/simulate_market.py`; decisions D84, D93, D95, D96.

**Everything the simulator produces is simulated data.** It stands in for real reviews and work
evidence until Phases 9–11 record them, and it is labelled "Simulated history" wherever it
shows. Its latent traits are ground truth for experiments only: they never enter the
application database or the UI.

## What it models

| Part | Model (one seeded `numpy.random.Generator`, PCG64, draws in a fixed order) |
|---|---|
| Developers | 1–3 primary domains; skill ~ Beta(5, 2) in them and Beta(2, 5) elsewhere; reliability, teamwork, communication ~ Beta(4, 2); price level ~ U(0.8, 1.3). About 30 % newcomers (0–2 projects), the rest 3–12 projects |
| Clients | budget margin ~ U(1.1, 1.4); rating strictness ~ U(−0.1, 0.1); a reviewer profile for trust (§9.14) |
| Projects | 3–8 milestones on a random DAG (edges only from earlier to later milestones, so acyclic by construction; every plan goes through `cpm.compute_cpm`); deadline = CPM duration × U(1.1, 1.4); a team of 2–5 whose prices the budget covers after the 5 % platform fee |
| Who hires whom | 30 % of the time a developer's next project comes from a client they already worked for; personas fix the number of distinct clients |
| Work span t | a share U(0.7, 1.0) of the CPM duration, stretched by exp(N((0.55 − reliability)·1.5 + (0.55 − skill)·0.3, 0.15)) |
| Client ratings | 1–5 stars around q = 0.6·skill + 0.4·reliability, plus strictness and noise (σ 0.08), normalised (r − 1)/4; one per pair of milestones plus the final review |
| Communication Γ | §9.1.4: 0.6·(0.5 on-time check-ins + 0.3 reply score + 0.2 claims) + 0.4 client's communication rating |
| Teamwork Γ_m | §9.1.5: 0.8 × trust-weighted mean of peer ratings + 0.2 × help given |
| External reviews | one verified external rating on about a quarter of projects |

Output per developer: the §9.1.1 inputs of each completed project (`SimProject.to_record()`), as
4-place decimal strings, plus the team's prices and budget. `market_to_json()` is canonical
(sorted keys), so the same seed gives byte-identical output.

## Personas (the stage-2 demo seed, D93)

`backend/scripts/seed_data/stage2_personas.json` fixes traits and history shape for the named
developers of §18.1, so their stories hold with computed reputations: Arif (8 projects, 5
clients, strong), Nusrat (strong), Imran (7 projects for one client, so client diversity 0),
Shakib (often late), Zahid (3 projects, D93), and Rafsan (one project, still a newcomer). The
seed stores their histories as SIMULATED `reputation_history` rows and runs the engine; the
result is pinned in `backend/tests/fixtures/stage2_reputation_golden.json`. Every bidder on the
"Online ordering system" stays eligible (P ≥ 0.45, C ≥ 0.40), so the documented 10 eligible
bids hold in stage 2 as in stage 1.

## Running it

```bash
cd backend && .venv/bin/python scripts/simulate_market.py --seed 2026 --developers 200 --out /tmp/market.json
make seed-demo STAGE=2          # on the demo stack (or make demo-up STAGE=2)
make reputation-recalculate     # recompute every reputation from its history
```

## Checks

`tests/algorithms/test_simulator.py`: same seed → identical bytes, different seeds differ,
trait and newcomer shares in range, 500 plans acyclic through `cpm.py`, budgets cover prices,
ground truth never in the records, personas keep their shape, invalid input refused, Spearman by
hand, and E5 (below).

## E5: does reputation track true ability? (D96)

Over the 141 experienced developers (≥ 3 projects) of seed 2026 with 200 developers, Spearman ρ
between computed **performance P** and latent quality (0.6 × skill + 0.4 × reliability) is
**0.797**, and between computed **competency C** and latent breadth and communication (0.7 ×
primary domains / 3 + 0.3 × communication) is **0.759**. The test requires ≥ 0.5 for both. Seeds
1, 7, 99 and 123 give 0.75–0.83 (P) and 0.68–0.78 (C).

*Investigation note.* A first latent target for C counted every domain where skill happened to
exceed 0.6, including domains the developer never works in, and correlated only 0.38–0.56 across
seeds. ω (Eq. 1) can observe only the domains of completed projects, so the latent counterpart is
the developer's primary domains; with that definition the correlation is stable. No reputation
setting was changed.

Limitations: simulated data, not real users; the model's own assumptions (Beta traits, linear
quality) shape the result; attack injection (rating rings, revenge reviews, shill bids) is added
with the integrity rules in Phase 11 (D90).
