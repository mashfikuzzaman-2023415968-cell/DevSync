# Phase 6 — Reputation engine and market simulator (plan)

> On approval this file is saved verbatim as `docs/plans/phase-06.md` (first commit on branch `phase-6`).
> Owner: Raisa Tabassum (with Claude Code). Spec: §17 Phase 6, §9.0, §9.1, §9.14 (trust formula), §7.7,
> §10.2 (Reputation), §11, §13.5 #16, §13.9 (Reputation page), §14.13 row 6, §16, §18.3–§18.4, §19 E5.

**Skills loaded for the frontend work:** `devsync-ui` (+ `references/components.md`) and `frontend-design`
(loaded before any screen code; `devsync-ui` wins). No 3D in this phase, so no `threejs-*`.

## Context

DevSync's research core is the [PCS] reputation model (Eq. 1–12). Since Phase 5, Algorithm 1 has read
**fixed** stage-1 snapshots for experienced developers (D44) and computes only `newcomer_snapshot()`.
Phase 6 implements the full model as pure functions, feeds it with **simulator-generated project
histories** (real reviews and evidence arrive in Phases 9–11), stores snapshots, per-skill competency and an
append-only explanation log, and shows them on the Reputation page (screen 16). `reputation_read.py` stays
the only read path, so filtering and the bid screens keep working unchanged; computed values flip the D48
"seeded" marker off. Stage 1 (Demo 1) is untouched; `make seed-demo STAGE=2` loads computed reputations.

Starting point verified on 2026-11-21 (Raisa's laptop, WSL 2): stack healthy, migrations at 0011, backend
unit 700 passed, frontend 501 passed, demo stack `ready (9/9)` with the documented 10 eligible bids.

## 0. First task — P6-0: Node 22 LTS (D15)

- `infra/nginx/Dockerfile` frontend stage `node:20-bookworm-slim@sha…` → `node:22-bookworm-slim@sha…`
  (digest of a tag ≥ 14 days old, D62g); `.github/workflows/ci.yml` `node-version: "22"`;
  `frontend/package.json` `engines.node` `">=22"`; add `frontend/.nvmrc` (`22`).
- Toolchain versions stay (Vite 6.4 / Vitest 4.1, D15); a Vite 8 / Vitest 5 upgrade is **not** part of this
  phase (recorded as a follow-up).
- Verify: rebuild nginx image, `npx vitest run`, `npm run build` (bundle budget), one E2E smoke
  (`home.spec.ts` on Chromium in the test stack). Record as **D83**; backlog P6-0 → done.

## Decisions to record (D84 onwards) — proposed, approve with the plan

- **D84 · Where Phase 6 inputs come from.** New table `reputation_history`: one row per completed project per
  developer, holding exactly the §9.1.1 inputs (domain, client key, t, T^d, Γ^n, Γ_m^n, internal slots,
  external slots, completed_at) with `source ∈ {SIMULATED, PLATFORM}`. The simulator writes SIMULATED rows;
  Phase 11's `reputation.update_project` will write PLATFORM rows from real evidence through the same
  pipeline. Simulated data is labelled "Simulated history" everywhere it shows (§0.2.6).
- **D85 · Arithmetic.** Equations run in `Decimal` (context of `core/money.py`'s style: precision 28);
  inputs are 4-place decimal strings; only stored outputs are rounded, `ROUND_HALF_UP` to 3 places
  (`numeric(4,3)`), as `newcomer_snapshot()` already does.
- **D86 · The change cap applies per project, in order.** For X, X_m and β, each project's new value is
  clamped to ±`rep.max_change_per_project` around the value after the previous project (starting from the
  newcomer values Γ⁰, Γ_m⁰, `rep.newcomer_review`); never to ω, μ, T. The log stores raw and capped values.
- **D87 · Missing externals across projects.** Eq. 8's EWMA runs over the projects that *have* verified
  external reviews, in order; with none, β = λ (A8).
- **D88 · Newcomer ω with history.** For N < 2, ω = ω⁰ (evidence domains); from N ≥ 2, Eq. 1 over projects.
- **D89 · `pcs_replication` in reputation.** Off: change cap; newcomer starting values (Γ⁰ = 0 and Γ_m⁰ = 0
  as the paper's "set to zero"; ω and μ for N < 2 and T with no projects = 0); evidence/trust weighting
  (all review weights 1); per-skill competency. Kept: A2 clip. Undefined values (N < 2) are listed in the
  output as replication resolutions and added to the §23 supervisor list.
- **D90 · Reviewer trust (§9.14 formula only).** Pure `algorithms/trust.py::reviewer_trust()` and the
  trust-weighted mean used to aggregate simulated reviews. Collusion/consistency rules, the `reviewer_trust`
  table and attack injection are Phase 11 (they need real reviews); the simulator exposes the hooks.
- **D91 · Ambiguity tests by phase.** Phase 6 writes `test_A1`, `A2`, `A4`, `A5`, `A6`, `A8`, `A9` (reputation);
  `A3`, `A7`, `A10`, `A13` arrive with Phase 7's fitness/BPSO, `A11` with Phase 10's payment policy, `A12`
  with Phase 15's experiments. `PAPER_ALIGNMENT.md` lists all 13 with their phase.
- **D92 · Admin recalculation moves to Phase 12.** The `reputation.recalculate_all` job and a CLI
  (`make reputation-recalculate`, used by the stage-2 seed) are built now; `POST /admin/reputation/recalculate`
  and the admin page need `GET /jobs/{id}` (Phase 7) and the admin console, so they move to Phase 12 and
  the admin nav marker becomes `phase: 12`. "Reputation updated" notifications go with Phase 11.
- **D93 · Stage-2 personas.** `seed_data/stage2_personas.json` fixes latent traits and history shape for
  the 14 seeded developers so the §18.1 stories hold (Arif strong, 8 projects / 5 clients; Imran 7 projects
  for one client → μ = 0; Shakib often late; Nusrat strong). Zahid keeps **3** projects (as the stage-1
  seed, not §18.1's "2": with 2 he is a newcomer and the documented 10-eligible result breaks).
- **D94 · Γ⁰ counts a verified certificate.** Bug fix: `_verified_items` counted phone, email and profile
  but not the verified certificate §9.1.3 lists (and its docstring claims). Fixed with tests.
- **D95 · Dependencies.** `numpy` (spec-named, §3), pinned exactly, ≥ 14 days old, for the simulator's
  seeded `Generator` (and Phase 7's PSO). No Recharts: the radar and trend charts are custom SVG like
  `Gantt.tsx` (CSP-proven), each with "View as table".
- **D96 · E5 as a test.** On simulator histories (seed 2026, 200 developers), Spearman ρ between computed P
  and latent quality must be ≥ 0.5 (and C vs latent skill ≥ 0.5); measured values go into `docs/ALGORITHMS.md`.
  If it fails, investigate before touching any setting.

## Database — migration `0012_reputation_engine` (written like 0006/0011, full downgrade)

| Table | Columns (beyond id/timestamps) | RLS (ENABLE + FORCE) |
|---|---|---|
| `reputation_history` | `developer_id`, `source (SIMULATED, PLATFORM)`, `project_id NULL`, `project_label text(≤120)`, `client_key text`, `domain skill_domain`, `skill_id NULL`, `t_days`, `deadline_days`, `gamma_comm`, `gamma_team`, `internal_slots numeric[]`, `external_slots numeric[]`, `completed_at`; UNIQUE(developer, source, project_label/project_id) | developer + admin read; SYSTEM write |
| `reputation_skill` | `developer_id`, `skill_id`, `competency numeric(4,3)`, `settings_version`; UNIQUE(dev, skill) | like snapshots: any signed-in read; SYSTEM write |
| `reputation_log` **AO** | `developer_id`, `history_id`, `project_id NULL`, `parameter`, `old`, `new`, `raw_new`, `inputs jsonb`, `formula_version`, `settings_version`, `reason_code`; UNIQUE(history_id, parameter, settings_version) | developer + admin read; SYSTEM insert; trigger raises on UPDATE/DELETE; app roles have no UPDATE/DELETE |

`reputation_snapshots` is unchanged; computed rows set `settings_version`. Grants, `migrator_all` policies,
upgrade → downgrade → upgrade and `alembic check`; `make erd` afterwards. `check_rls.py` covers the new tables.

## Backend — algorithms (PURE, Decimal, ≥ 95% coverage, `check_layers` clean)

- `algorithms/reputation.py`: keep `newcomer_snapshot()`; add one function per equation, each docstring naming
  it — `eq01_omega`, `eq02_communication`, `eq03_teamwork`, `eq04_competency`, `eq05_external_within`,
  `eq06_internal_within`, `eq07_internal_across`, `eq08_external_across`, `eq09_beta`, `eq10_mu`,
  `eq11_timeliness`, `eq12_performance`; `apply_change_cap`; `skill_competency` (§9.1.7);
  `platform_mean_beta`; `compute_snapshot(history, evidence, params) -> SnapshotResult` (snapshot,
  per-skill competency, and a per-project trace of every parameter: old, raw, capped, inputs). `ReputationParams`
  is built from settings (extends `NewcomerParams`; includes `mode`).
- `algorithms/reputation_explain.py`: plain-language "Why did this change?" sentences from trace entries
  (e.g. "Punctuality 50 → 55: finished in 18 of 30 days"); unknown codes dropped (like D65).
- `algorithms/trust.py`: §9.14 `reviewer_trust()` and `trust_weighted_mean()`.
- `algorithms/simulator.py`: the §18.3 market model with a seeded `numpy.random.Generator` — latent traits
  (per-domain skill ~ Beta, reliability, teamwork, communication, price level), ~30% newcomers, clients with
  budgets and strictness, projects with 3–8 milestones on a random DAG (acyclic by construction, checked
  with `cpm.py`), budgets consistent with prices, outcomes from traits + noise → `reputation_history`-shaped
  records; persona overrides for the seed. Output is plain dataclasses / JSON; ground truth is never stored
  in the app DB.

## Backend — services, jobs, routes, schemas

- `services/reputation_inputs.py`: builds `DeveloperHistory` from `reputation_history` rows plus newcomer
  evidence (verified items incl. certificate, evidence domains — reuse `reputation_read._verified_items` /
  `_evidence_domains`, moved here and shared).
- `services/reputation_engine.py`: `recalculate(ctx, developer_id)` and `recalculate_all(ctx)` in a SYSTEM
  session: two passes (experienced first for `platform_mean_beta` when `rep.newcomer_review` is null), upsert
  snapshot + `reputation_skill`, insert log rows idempotently (unique key → re-running is a no-op), audit entry.
- `services/reputation_read.py`: shape unchanged (D44/D58); computed snapshots report `seeded=false`; adds
  `read_skill_competency()` for Phase 7.
- `services/reputation.py` (view): developer reputation view and the developer's own history page.
- `jobs/reputation_jobs.py`: `reputation.recalculate_all` (RQ timeout 30 min, 0 retries, `run_recorded`).
- `scripts/simulate_market.py` (CLI: `--seed --developers --out file.json`); `scripts/seed_demo.py --stage 2`
  = stage 1 + persona histories → recalculate → assert golden values and that the ordering project still
  gives **10 eligible** (TOO_SLOW Shakib, NO_SKILL_EVIDENCE Lamia); `scripts/reputation_recalculate.py`
  (+ `make reputation-recalculate`); Makefile `seed-demo STAGE=2`, `demo-up STAGE=2` work.
- Test-only router: `POST /__test__/developers/{id}/reputation-history` (SIMULATED rows + recalculate).

### Endpoints (contract-first; examples and declared errors on every operation)

| Method & path | Who | Request | 200 response | Errors |
|---|---|---|---|---|
| GET `/developers/{id}/reputation` | any active signed-in user (`reputation.read`); hidden like `GET /developers/{id}` (clients-only profiles → 404 for developers) | path uuid | `DeveloperReputation {developer_id, parameters{omega,x,xm,beta,mu,t}, competency, performance, completed_projects, distinct_clients, is_newcomer, seeded, simulated, skills[{skill_id,name,competency}], newcomer: {verified_items, evidence_domains}|null, updated_at}` (3-place decimal strings) | 401, 403, 404, 422, 429 |
| GET `/me/reputation/history?cursor&limit` | developer (self) | cursor ≤ 200 chars, limit 1–100 | `Page[ReputationChange] {history_id, project_label, completed_at, simulated, changes[{parameter, old, new, raw_new, capped, reason}]}` | 401, 403, 422, 429 |

No request bodies (no `StrictRequest` needed); both added to the authz matrix and fuzzing; `make openapi`
(after rebuilding the test image) and `npm run api:types`.

## Frontend (devsync-ui + frontend-design; mobile-first; four states; light/dark)

- `features/reputation/`: `ReputationPage` (`/dev/reputation`, screen 16 per §13.9 layout): page header
  ("Your reputation", "Newcomer · 1 of 3 projects done"), `ReputationPanel`, `RadarChart`, `TrendChart`
  (custom SVG, keyboard-focusable points, tooltips, "View as table"), "Why did this change?" list,
  per-project contribution history, `NewcomerCard` explaining starting values; "Simulated history" label.
- `components/ReputationPanel.tsx` (reusable, §13.3): six meters with plain labels (Expertise,
  Communication, Teamwork, Quality, Client diversity, Punctuality), C and P as 0–100, "show evidence"
  accordions; paper symbols only inside the explanation drawer.
- Profiles (screens 7/9) and the client bids table: keep the summary; the "seeded" marker disappears for
  computed values; developer profile links to the full breakdown.
- Navigation: dev "Reputation" placeholder → real route; admin "Reputation" → `phase: 12`.
- Motion from `motion.ts` only (meters 400 ms, count-up once; nothing loops); reduced motion respected.
- Tests: every component, hook and formatter (Vitest + MSW): four states, newcomer vs experienced, table
  alternative, a11y; `e2e/phase6.spec.ts` (`@e2e`): experienced and newcomer pages read correctly; screens
  added to `screens.ts` / `stateful-screens.ts` (axe, responsive matrix 375/390/768/1366/1440, visual
  baselines via `make visual-update`, noted in PROGRESS.md); CSP check on the page.

## Security (§14.13 row 6)

- Inputs only from server-side evidence: no endpoint writes reputation; `reputation_history`, snapshots, skill
  rows and the log are SYSTEM-write under RLS; web sessions can't claim SYSTEM (existing tests extended).
- `reputation_log` append-only (trigger + no grants), tested at the DB level.
- History and log readable only by the developer and admins (RLS + authz); IDOR tests; GETs don't mutate.
- Settings validation (κ ≤ 0.5, α_x/α_e ≥ 0.5, sums ≠ 1 rejected) — existing validators, new named tests.
- Ground truth from the simulator never reaches the DB or API.

## Tests (no happy-path-only)

1. **Equations by hand:** `test_eq01_…` … `test_eq12_…`, ≥ 2 fixtures each with arithmetic in the docstring:
   ω {2,1,1} → 0.8333; μ 4 clients → 1, same client ×4 → 0; an Eq. 2 EWMA sequence; Eq. 5–8 slots and
   cross-project with α_x < 0.5 (older weigh more); Eq. 11 with the clip; Eq. 12 weights.
2. **Ambiguities:** `test_A1_timeliness_direction`, `A2`, `A4`, `A5`, `A6`, `A8`, `A9` (default + alternative).
3. **`pcs_replication`:** one test per switched-off extension (cap, newcomer values, trust weighting, skill
   competency) and A2 kept.
4. **Properties (Hypothesis):** outputs in [0,1]; higher rating never lowers β; more distinct clients never
   lowers μ; ω independent of project order; cap never exceeded for X/X_m/β and never applied to ω/μ/T;
   newcomer values exactly §9.1.3.
5. **Settings:** κ ≤ 0.5, α_x ≥ 0.5, weights ≠ 1 rejected on save.
6. **Simulator:** same seed byte-identical JSON; different seeds differ; trait and newcomer shares in range;
   every plan acyclic via `cpm.py`; budgets ≥ Σ prices.
7. **E5:** Spearman ρ ≥ 0.5 (D96).
8. **Golden snapshot:** stage-2 values for named developers in `tests/fixtures/stage2_reputation_golden.json`.
9. **Perf (`perf`):** 50-project history < 20 ms.
10. **Unit/API/integration/jobs/security:** every service function and rule; both endpoints (success,
    validation, authz, IDOR, visibility 404); RLS cross-user per new table; append-only; job idempotency and
    recorded run (`jobs` marker); D94 certificate fix; stage-1 seed still asserts 10 eligible.

## Gate (P6 additions)

- `phase6_checks` = `phase5_checks` + `scripts/check_paper_alignment.py` (every Eq. 1–12 id listed in
  `docs/PAPER_ALIGNMENT.md` with a function and appearing in a test name) + stage-2 seed golden assertion +
  plan exists; registered in `step_phase_checks`.
- Perf test joins step 16; coverage 85% / 70%, `app/algorithms/` ≥ 95%; E2E Chromium only.
- **Gate machine:** step 16 needs a real GPU through `/dev/dri`; this WSL laptop very likely can't pass it
  (D28). Before the full gate I run the `@perf|@gpu` step alone here; if it fails, the gate runs on a native
  Linux laptop (to arrange with Taeen).

## Docs and records

`docs/PAPER_ALIGNMENT.md` (Eq. 1–12 + A1–A13 with phase), `docs/ALGORITHMS.md` reputation section with a
worked example and measured E5 values, `docs/SIMULATOR.md`, `docs/API.md`, `docs/SECURITY.md`,
`docs/TESTING.md`, `docs/BACKLOG.md` (P6-0, FR-REP-1/2/4/5/6), `DECISIONS.md` D83+, `PROGRESS.md`
(and correct its stale "Current phase" line), `docs/security-reviews/phase-06.md` after `/security-review`.

## Order of work

1. Branch `phase-6`; save this plan; P6-0 (Node 22) + D83.
2. Pure algorithms + their tests (equations, A-tests, properties, trust), then simulator + tests, E5.
3. Migration 0012 + models + RLS/append-only tests; ERD.
4. Services, job, CLI, test router; stage-2 seed + golden fixture; D94 fix.
5. Endpoints + contract + authz matrix + fuzz; OpenAPI + frontend types.
6. Frontend page and components; E2E, axe, visual baselines.
7. Docs; `/security-review`; GPU step check; `make gate PHASE=6`; PROGRESS; commit `phase-6: …`, tag, push.

## Verification

- Fast loops: `.venv/bin/pytest -m "unit or property"` and `npx vitest run` after each step.
- `make seed-demo STAGE=2` prints computed reputations and still "10 eligible"; `make demo-up STAGE=1`
  and `e2e/demos/demo-1.spec.ts` still pass.
- Manual: open `/dev/reputation` as Arif (experienced) and Nadia (newcomer); explanations read sensibly.
- `make gate PHASE=6` prints `PHASE 6 GATE: PASS`.

## Risks and open questions

- **Demo 2 (7 Dec) is 16 days away** with Phases 6–12 left and 8–12 unassigned; confirm date and owners
  with Taeen. Phase 6 target: about 4 days.
- GPU gate step on WSL (above).
- Supervisor answers (§23) still pending; defaults stand; D89's replication resolutions added to the list.
- Push access for Raisa's GitHub account.
