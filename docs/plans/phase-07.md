# Phase 7 — Team formation (plan)

> On approval this file is saved verbatim as `docs/plans/phase-07.md` (first commit on branch `phase-7`,
> created from `main` = `9da1ce7`, the Phase 6 merge). Owner: Raisa Tabassum (with Claude Code).
> Spec: §17 Phase 7, §9.2–§9.8, §7.4, §8, §10.1–§10.4, §11, §12, §13.2, §13.5 #12 and #24, §13.9,
> §14.13 row 7, §16.4–§16.5, §19 E1. Next decision number: **D103**.

**Skills for the frontend work:** `devsync-ui` (+ `references/components.md`) and `frontend-design`
(loaded before any screen code; `devsync-ui` wins). The homepage % chip touches the 3D hero's HTML
chip only, so the `threejs-*` skills are loaded for that step and `make stills` is re-run.

## Context

Phase 7 is the research core of Demo 2: the client turns the Algorithm 1 shortlist into a **fair,
explained, verified team**. It implements [PCS] fitness (Eq. 17–19) and binary PSO (Algorithm 2,
Eq. 13–16) exactly as §9.3, plus our extensions: the repair operator, the exact solver used to
verify small runs, the fairness dial with the cost of fairness, team comparison, "why this team"
with risks, and "why not selected" with a price counterfactual. Runs are saved and reproducible
(snapshot + parameters + seed), run as a background job with live progress over the project's
first **SSE** endpoint, and confirming a run creates the team and its (not yet sent) invitations.

## 0. Carried over from Phase 6 (first commits)

Two changes were made on the Phase 6 branch after it went to the gate and are not on `main`
(they are kept on the local branch `phase-6-local`):
- **Audit-chain race fix** (migration `0013_audit_chain_order`): a row now takes its `seq` *after*
  the chain lock, so concurrent writers can't fork the chain and trip `audit_verify_chain()`
  (seen in the first Phase 6 gate run). Deterministic test included. Re-recorded as **D103**
  (it was D102 locally; `main`'s D102 is the search-budget fix).
- **CSP and axe checks one test per screen** (extends D100), so a slow screen can't exhaust a
  role's shared 60 s budget. Same checks; recorded in **D104**.

## Decisions to record (D105 onwards) — proposed, approve with the plan

- **D105 · Arithmetic.** PSO and fitness run in NumPy float64 (spec allows); every stored or shown
  score is rounded half-up to 3 places (fitness to 4 internally, 2 on screen per §13.8), money stays
  integer paisa (prices, budget, counterfactuals). A float-free tie-break (bid id) keeps
  determinism.
- **D106 · How a run starts.** The client posts thresholds within the D54 bounds, a preset
  (Quality→P, Balanced→C, Fast→t, Budget→c), weights C1–C4 (normalised server-side) and
  `min_newcomers` 0–2. The server re-runs Algorithm 1 through `services/bids.evaluate()` +
  `filter_bids` with those values (no copied filtering logic), freezes the per-slot shortlist as the
  candidate snapshot, generates the seed itself (a body `seed` is 422), and enqueues the job.
  Starting the first run while BIDDING closes bidding: `BIDDING → FORMING` with the verdicts recorded
  exactly as the deadline job does (D64).
- **D107 · Jobs API and SSE are generic.** `GET /jobs/{id}` and `GET /jobs/{id}/events` serve any
  job with a requester (requester or admin; others 404). Progress is published to Redis
  (`job:{id}:events`, capped list + `progress`) by the worker; the SSE endpoint follows it with a
  20 s heartbeat, closes after 30 min, refuses a foreign Origin (403) and a 4th concurrent stream
  (429, Redis counter `sse.concurrent`), and carries only ids, progress, iteration and best fitness.
  Nginx gets a dedicated `/api/v1/jobs/…/events` location: `proxy_buffering off`,
  `X-Accel-Buffering: no`, read timeout 60 s.
- **D108 · Invitations are created but not sent in Phase 7.** Confirm creates the team
  (TEAM_PENDING), members (INVITED), TENTATIVE reservations (§9.17) and invitation rows with
  `sent_at`/`expires_at` NULL. Phase 8 sends them (the 48 h clock starts then), so a developer is
  never told about an invitation they can't answer yet. Phase 7 sends "Team formation finished"
  (client) and, on confirm, "Not selected" (each non-selected bidder, link to the bid's
  explanation). "Selected" goes with Phase 8.
- **D109 · Saved runs.** Each project keeps its runs; the client sees them through
  `GET /projects/{id}/formation-runs` (newest first; not in the §10 table, added for "earlier runs"
  and Recalculate). Re-running a stored run's snapshot + params + seed gives the identical result
  (tested; the admin verify endpoint re-checks it).
- **D110 · Admin pieces.** `POST /formation-runs/{id}/verify` (admin, step-up as §10.2's admin
  algorithm actions) and `GET /admin/formation-runs` (API) are built now; the admin page and the
  client "Teams" page move to Phases 12 and 8 (nav markers updated: admin "Team formation runs" →
  12, client "Teams" → 8).
- **D111 · Paper findings resolved (D9 items 1 and 3).** A3: infeasible = −∞ (paper prints −1;
  a feasible fitness can be below −1) — `test_A3_infeasible_fitness`. Initialisation: positions
  Bernoulli(N/k), velocities U(b_l, b_u) (paper: positions U(b_l, b_u), velocities U(−|b|, |b|)) —
  `test_initialisation_resolution`. Both listed in `PAPER_ALIGNMENT.md`.
- **D112 · Optimality thresholds and E1.** PSO vs exact on 200 seeded random small instances:
  optimal ≥ 95 %, mean gap ≤ 2 % (§17); per-instance data written to `runs/experiments/e1.csv`
  (simulated, labelled). Gate smoke: 20 instances.
- **D113 · Homepage figures (P7-H, D21).** `scripts/build_homepage_example.py` runs filtering + PSO
  + fairness on the §18.2 sample and writes `src/content/homepage-example.json`; the hero chip shows
  the real cost-of-fairness %; the gate checks the file is fresh (hash of inputs + algorithm
  version).

## Database — migration `0014_team_formation` (written like 0006/0012, full downgrade)

| Table | Key columns | RLS |
|---|---|---|
| `formation_runs` | project, requested_by, `status run_status` (QUEUED, RUNNING, SUCCEEDED, INFEASIBLE, FAILED, TIMED_OUT), settings_version, `params jsonb`, `candidate_snapshot jsonb` (immutable: trigger), `result jsonb`, runtime_ms, error_code, job_id | project client + admin read; SYSTEM writes; snapshot/params/seed immutable after insert (trigger) |
| `bid_explanations` | bid, run, `reasons jsonb`, price_counterfactual_paisa, main_gap | bidder + admin only (sealed, §14.13 row 7) |
| `teams` | project UNIQUE, status, confirmed_at | client, members, admin |
| `team_members` | team, developer, bid, slot, price_paisa, days_needed, is_lead, `status member_status`, joined_at, left_at, left_reason; partial unique lead | client, members, admin |
| `invitations` | team_member, sent_at, expires_at, responded_at, response, is_replacement | invitee, client, admin |

All ENABLE + FORCE, `is_system()` for SYSTEM writes (D99 pattern), `check_rls.py`, demo-reset
classification, ERD.

## Backend — algorithms (PURE, ≥ 95 % coverage, seeded `numpy.random.Generator`)

- `fitness.py` — Eq. 17–19 with per-member breakdown {comp, team, time, cost} (+ optional C5·P,
  A7; `fitness.use_skill_competency` switches C_i to C_{i,s}); `feasible()` (size, slot counts,
  distinct developers, budget after fee (A10), coverage, min newcomers); weights normalised.
- `bpso.py` — Algorithm 2: Bernoulli init, Eq. 14 velocity with inertia, clamp v_max, Eq. 15–16
  sigmoid, repair operator (§9.3 steps 1–5, locks never removed), pbest/gbest, archive of distinct
  feasible teams, early stop, timeout (injected deadline, no clock in `algorithms/`), convergence
  history, progress callback.
- `exact_solver.py` — Cartesian product of per-slot combinations; refuses above
  `exact.max_candidates` / `exact.max_combinations`; best, top 3 distinct, count.
- `fairness.py` — two runs (k = 0 and k) with the same seed; cost (F0 − Fk)/|F0| (0 when F0 ≤ 0 or
  not binding), price difference, newcomers included, maximum feasible k fallback with reason.
- `explain.py` — why this team (coverage, budget, schedule, newcomers, member contributions,
  runner-up difference, relaxations, verification), risk chips (`SINGLE_POINT_SKILL`,
  `BUDGET_TIGHT` > 95 %, `SCHEDULE_TIGHT` > 90 %, `LOW_TEAMWORK` < 0.5,
  `NEWCOMER_ON_CRITICAL_PATH`), comparison of top teams, why not selected (filter reasons via
  `filtering.explain_bid`, forced-inclusion gap, price counterfactual by 10-step binary search on
  φ ∈ [0.5, 1] rounded down to ৳100, main gap with hint; cap 50).
- `pcs_replication`: no repair, clamp, newcomer minimum or fairness dial; infeasible → A3 only;
  inertia 1.0 (A13).

## Backend — services, jobs, routes

- `services/formation.py` — start (authz, quota `ratelimit.formation_run` 10/h + 1 concurrent per
  project, Idempotency-Key via `core/idempotency.py` like role-assessment start, snapshot in a SYSTEM
  session per D50, enqueue), read run, list runs, confirm (FORMING → TEAM_PENDING; bids SELECTED /
  NOT_SELECTED; team, members, invitations, tentative reservations; notifications; audit), admin
  verify. Transitions through the existing transition-table pattern (409 `INVALID_STATE`).
- `services/jobs_api.py` + `core/sse.py` — generic job status and event stream (D107).
- `jobs/formation_jobs.py` — `formation.run` (60 s, no retry; QUEUED → RUNNING → SUCCEEDED |
  INFEASIBLE | FAILED | TIMED_OUT with best feasible team) and `formation.explanations` (120 s,
  1 retry; idempotent per run).
- Endpoints (contract-first, examples and declared errors on each):

| Method & path | Who | Notes |
|---|---|---|
| POST `/projects/{id}/formation-runs` | client (own) | Idempotency-Key; body: preset, weights, p0, c0, min_newcomers; 202 `JobAccepted` + run id |
| GET `/projects/{id}/formation-runs` | client (own), admin | saved runs, newest first (D109) |
| GET `/formation-runs/{id}` | client (own), admin | result, breakdown, risks, top teams, cost of fairness, convergence, relaxations, verification |
| POST `/formation-runs/{id}/confirm` | client (own) | creates team + invitation records (D108) |
| POST `/formation-runs/{id}/verify` | admin (step-up) | exact verification / reproduction |
| GET `/admin/formation-runs` | admin | page |
| GET `/bids/{id}/explanation` | bidder, admin | why not selected |
| GET `/jobs/{id}` · GET `/jobs/{id}/events` | requester, admin | generic (D107) |

- Nginx SSE location; `tests/edge/test_edge.py` streams through Nginx.
- Test-only router: finish a formation run for E2E seeding if needed.

## Frontend (devsync-ui + frontend-design; mobile-first; four states; light/dark)

- **Screen 24** `/client/projects/:id/formation` per §13.9: settings (presets, `PrioritySliders`
  with linked normalisation to 100 %, minimum standards with live "x of y bids pass", `FairnessDial`
  0/1/2, "Form team"); running state (SSE progress, live `ConvergenceChart`, the swarm indicator —
  the only looping animation, only while running); result (stat row: fitness, price of budget,
  finish days, "✓ Optimal" / gap %, cost of fairness; `TeamCard`s with the flip-in token and
  contribution bars; "Why this team?"; `TeamComparison` top 3; earlier runs; "Recalculate";
  "Confirm team" with `ConfirmDialog`).
- **Screen 12** "Why not selected" card on `/dev/bids/:id`.
- Entry point from the client Bids page; nav markers per D110.
- Charts custom SVG (CSP-proven), "View as table", sized to their container (Phase 6 pattern).
- Homepage hero % chip from `homepage-example.json` (D113); `make stills`.
- Tests: every component and hook (Vitest + MSW, four states, keyboard, reduced motion);
  `e2e/phase7.spec.ts` (`@e2e`); screens in `stateful-screens.ts`; axe, responsive, CSP, visual
  baselines (`make visual-update`, reviewed).

## Security (§14.13 row 7, §16.4)

Quotas (10/h, 1 concurrent per project), Idempotency-Key, job and RQ timeouts; candidate snapshot
immutable (DB trigger); explanations visible only to the bidder and admins (authz **and** RLS, with
a response-scanning test like `test_role_assessment_api.py`); only the project's client runs and
confirms, only admins verify; mass assignment (`status`, `seed`, `result`, `is_lead`,
`candidate_snapshot`) → 422; malicious client (weights not summing, `min_newcomers` > team size,
out-of-range thresholds, oversized bodies) refused; SSE needs a session, refuses foreign Origin,
other users' jobs (404) and a 4th stream; RLS cross-user tests per table; authz matrix + fuzzing for
every route.

## Tests (no happy-path-only)

1. Fitness by hand: 2- and 3-member teams with docstring arithmetic; −∞ (A3); C5·P (A7); per-skill
   switch; weights normalised. `test_A3_…`, `test_A7_…`, `test_A10_…`, `test_A13_…` (D91).
2. Feasibility rules, one test each.
3. Repair invariants (Hypothesis): feasible or flagged; locks kept; idempotent on feasible input.
4. Determinism: same snapshot + params + seed → same team, fitness, convergence (also via the job
   and the stored run).
5. Optimality vs exact: 200 instances, ≥ 95 % optimal, mean gap ≤ 2 % (D112); E1 CSV.
6. Convergence: gbest never decreases; early stop; timeout returns best feasible with `timed_out`.
7. Exact solver: matches brute force on tiny cases; top 3 + count; refuses over limits; 18
   candidates < 3 s.
8. Fairness: cost ≥ 0, 0 when not binding, 0 when F0 ≤ 0; maximum feasible k fallback; dial 1 on
   the seeded "Online ordering system" selects a newcomer.
9. Explanations: counterfactual re-run selects the bid (property); main gap = largest weighted gap;
   filter reasons for rejected/not shortlisted; cap 50; risk chips at their exact boundaries.
10. Behaviour: Budget preset total price ≤ Quality's; Quality mean C ≥ Budget's; raising the cost
    weight never raises the best team's price (exact-solvable); presets map to advancement;
    recalculating with another preset can change the team.
11. Greedy baseline (E3's) comparison on simulated jobs, reported in `docs/ALGORITHMS.md`.
12. `pcs_replication`: repair, clamp, newcomer rule, dial off; A3; A13.
13. Security list above; jobs with `SimpleWorker` (idempotency, retry count, timeout → TIMED_OUT).
14. Perf (`perf`): |S| = 200, N = 10 < 5 s; exact 18 candidates < 3 s.
15. E2E (§17): dial 1 on the seeded project → newcomer selected, cost of fairness, "Optimal";
    compare; recalculate with Budget (team changes); confirm; a non-selected developer reads a
    correct explanation.
16. Manual: each preset and fairness level, explanations read aloud.

## Gate (P7 additions)

`phase7_checks` = `phase6_checks` + the seeded project's run with a fixed seed reproduces the team in
`tests/fixtures/formation_expected_team.json` + E1 smoke (20 instances) + homepage example fresh.
Perf budgets in step 16. The gate runs on a native Linux laptop with an Intel/AMD GPU (WSL can't
pass step 16 or the step timeouts, as seen in Phase 6).

## Order of work

1. P7-0 carry-overs (D103, D104).
2. Pure algorithms + tests (fitness, bpso, exact, fairness, explain), E1 and perf.
3. Migration 0014 + models + RLS/immutability tests.
4. Jobs API + SSE + Nginx location + edge test.
5. Formation service, jobs, endpoints, contract, authz matrix, fuzzing.
6. Frontend screen 24, "why not selected", homepage chip; E2E, axe, visual.
7. Docs (ALGORITHMS, PAPER_ALIGNMENT, API, SECURITY, TESTING), `/security-review`,
   `docs/security-reviews/phase-07.md`, PROGRESS; commit; gate on the native Linux laptop.

## Verification

Fast loops (`pytest -m "unit or property"`, `vitest`) per step; integration, jobs and API suites in the
test stack; `make seed-demo STAGE=2` then a formation run on "Online ordering system" by hand;
Phase 7 E2E, axe, responsive and visual locally; `make gate PHASE=7` on the native Linux laptop.

## Risks and open questions

- **Size and Demo 2 (7 Dec):** this is the largest phase. If time runs short, §17.0 allows moving
  team comparison to Demo 3; the research core (BPSO, exact verification, fairness dial) never moves.
- Gate machine: native Linux with an Intel/AMD GPU (WSL cannot pass).
- Supervisor answers (§23) still pending: A3, A7, A13 and the initialisation resolution use the
  documented defaults.
- Push access: a fresh token (please revoke the one shared in chat).
