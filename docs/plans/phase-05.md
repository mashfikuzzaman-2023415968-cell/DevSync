# Phase 5 — Marketplace, sealed bidding, Algorithm 1 filtering (plan)

*Demo 1 phase (Mon 2 Nov 2026). Owner: Salwa Baki, with Claude Code. Skills loaded for the
frontend work: `devsync-ui` + `frontend-design`.*

## Context

Developers find projects (search + recommendations), place **sealed** bids, and see a **live
eligibility preview**; the client sees every bid with eligibility reasons and handles the
too-few-bids case. Eligibility is **Algorithm 1** ([PCS] §4.2) plus our newcomer rule,
relaxation and advancement ordering (§9.2). No double booking (availability reservations, §9.17).
This is the last Demo 1 phase, so it also lands the **Demo 1 seed and tooling** (`make seed-demo
STAGE=1`, `demo-check`, `demo-up`, `demo-reset`, `demo-preflight`, `e2e/demos/demo-1.spec.ts`).

**Reputation dependency (important, §17 Phase 5):** Algorithm 1 needs each developer's `P` and
`C`, but the reputation *engine* is Phase 6. So Phase 5 creates `reputation_snapshots` + a read
API, implements **only** `newcomer_snapshot()` in `algorithms/reputation.py` (§9.1.3), and loads
**fixed** snapshots for the 9 experienced seeded developers from
`backend/scripts/seed_data/stage1_reputation.json` (values in §18.4). Filtering reads snapshots
**only** through `services/reputation_read.py`, so Phase 6 swaps seeded for computed values
without touching filtering. Snapshot values show a "seeded" marker **in development only**.

**The Phase 4 lesson is binding here:** mocked tests can't catch a wrong URL, a missing endpoint
or a sealed-bid leak. So `e2e/phase5.spec.ts` (real stack) and the sealed-bid RLS/authz tests are
written **early** and every frontend call targets an endpoint that exists in
`docs/api/openapi.json`.

## Dependencies (all present on `main` after Phase 4)

- `app/services/projects.py` — project status, publish, the `BIDDING` state; `BIDDING` is the
  only status a bid may be placed against.
- `app/models/projects.py` — `Project`, `ProjectSlot`, `Milestone`, status enums.
- `app/models/profiles.py::SkillEvidence` (`user_id, skill_id, score 0–1, source, at`) — feeds the
  newcomer rule (score ≥ `newcomer.pass_mark`) and `newcomer_snapshot()`.
- `e2e/fixtures.ts::createOrderingProject()` — builds the §18.2 plan through the API; reused by
  the Phase 5 E2E and seed.
- `core/authz.py` policy registry + matrix test; `core/ratelimit.py`; RLS foundation (§14.15).

## Decisions to record (D44 onwards)

- **D44 — fixed reputation snapshots in Phase 5.** Experienced developers get hand-set snapshot
  values (§18.4); only `newcomer_snapshot()` is computed. The seed script recomputes `C` (Eq. 4)
  and `P` (Eq. 12) from the stored sub-scores and **asserts** them so the table can't drift.
  *Why:* the reputation engine is Phase 6; filtering must be demonstrable at Demo 1. Read path is
  `services/reputation_read.py` only.
- **D45 — eligibility dry-run endpoint.** `POST /projects/{id}/bids/eligibility` (developer, not
  persisted) returns per-constraint pass/fail + the would-be reason for the bid sheet's live
  preview. *(Not spelled out in the §10 table; proposed — see Open questions Q2.)*
- **D46 — shortlist size.** Resolve the §9.2 (`max(3·count_s, 6)` per slot) vs §6.2
  (`max(3·N, 20)`) discrepancy. *Proposed:* follow §9.2 per-slot `K_s = max(3·count_s, 6)` (it is
  the algorithm text and is per-slot, which is what PSO consumes). Flag as Q1; record the choice.
- **D47 — too-few-bids actions in Phase 5.** The banner offers extend / lower standards / raise
  budget / reduce team / cancel. "Lower standards" and "reduce team" **re-plan** (edit P0/C0 or
  slots). In Phase 5, "reduce team" edits slots only while still `BIDDING`; formation itself is
  Phase 7, so "lower standards" stores client overrides on the project for the Phase 7 run and is
  reflected immediately in the eligibility preview counts.
- **D48 — "seeded" reputation marker.** `reputation_read` returns `seeded: bool`; the bid table
  and profile show the marker only when `settings.env != production`.

## Database — migration `0006_marketplace_bidding`

New enums: `bid_status` (ACTIVE, WITHDRAWN, INELIGIBLE, SELECTED, NOT_SELECTED, ACCEPTED,
DECLINED, EXPIRED — full set up front per the D38 precedent), `reservation_status` (TENTATIVE,
CONFIRMED, RELEASED).

Tables (§7.4, §7.7):
- `bids` — `project_id, developer_id, slot_id, price_paisa BIGINT, days_needed smallint,
  proposal(≤3000), expected_contribution(≤500), portfolio_item_ids uuid[] (≤3),
  hours_per_week_committed smallint, status bid_status, ineligible_reasons jsonb`. **UNIQUE(project,
  developer)**. CHECKs: `price_paisa > 0`, `1 ≤ days_needed ≤ 365`, array length ≤ 3.
- `availability_reservations` — `developer_id, project_id, hours_per_week, from_date, to_date,
  status reservation_status`. Index `(developer_id, status)`.
- `reputation_snapshots` — exactly §7.7 columns (`developer_id UNIQUE, omega, X, Xm, beta, mu, T,
  C, P, completed_projects, distinct_clients, settings_version, updated_at`); all scores
  `numeric(4,3)` with `BETWEEN 0 AND 1` CHECKs.
- **Projects search:** add a `search_vector tsvector` **generated** column
  (`to_tsvector('simple', title || ' ' || summary)`) + a GIN index; skills are joined in at query
  time (a project's slot skills) via a second GIN on a skills-name expression or a maintained
  column — *decide in build; generated column preferred for immutability.*

RLS (§14.15, §14.13 row 5) — ENABLE **and** FORCE on all three new tables:
- `bids`, `availability_reservations`: SELECT when `bidder = app_uid()` OR
  `is_project_client(project_id)` OR `is_admin()` — **never other developers** (sealed). INSERT/
  UPDATE when `bidder = app_uid()` and the project is `BIDDING` (a `SECURITY DEFINER`
  `project_is_bidding(project_id)` helper, pinned `search_path`, EXECUTE revoked from PUBLIC).
- `reputation_snapshots`: SELECT any authenticated user (public value); INSERT/UPDATE **SYSTEM
  only** (seed/Phase 6). GUEST sees nothing.
- Triggers: `bids` content immutable after a terminal status (WITHDRAWN/SELECTED/NOT_SELECTED/…);
  `guard_bid_project_bidding` rejects insert/price/days edits unless `BIDDING`.
- Add rows to nothing in `rls_exempt.yml` (all protected). `check_rls.py` must stay at 0
  unprotected.

DB-verify: upgrade → downgrade → upgrade on an empty DB; `alembic check` no drift; `check_rls` 0
unprotected; RLS integration tests (below) prove sealing as the web role.

## Backend — algorithms (PURE, deterministic, ≥ 95% coverage, `check_layers` clean)

`app/algorithms/filtering.py` — **Algorithm 1 + newcomer rule + relaxation + advancement + reasons**
(§9.2). Dataclasses only; no DB/web/clock. Scores on 0–1.
- `BidInput(bid_id, slot_id, skill_id, developer_id, is_newcomer, P, C, t_days, c_paisa,
  skill_evidence_score|None, has_slot_skill, active, available, self_dealing_flag)`.
- `ProjectInput(deadline_days T^d, budget_after_fee C''_j, slots={slot_id: (skill_id, count)})`.
- `FilterParams(P0, C0, advancement a∈{P,C,t,c}, team_size, newcomer_pass_mark,
  newcomer_competency_check=False, relax_step=0.05, relax_max_steps=3, shortlist_factor=3)`.
- Steps exactly as §9.2: (1) paper constraints `P≥P0, C≥C0, t≤T^d, c≤C''_j`; (2) newcomer rule
  (replace P0 check with `skill_evidence_score ≥ pass_mark`; C check only if
  `newcomer_competency_check`); (3) other gates (active, slot skill present, availability,
  no confirmed SELF_DEALING with this client); (4) relaxation −0.05 ×≤3, each step **reported**,
  never below 0; (5) advancement ordering per `a`, shortlist `K_s = max(3·count_s, 6)` (D46);
  (6) `FilterResult(eligible, shortlisted, rejected: list[(bid_id, ReasonCode)], relaxations)`.
- Reason codes (stable): `LOW_PERFORMANCE, LOW_COMPETENCY, TOO_SLOW, OVER_BUDGET,
  NO_SKILL_EVIDENCE, SKILL_MISMATCH, UNAVAILABLE, SUSPENDED, SELF_DEALING, NOT_SHORTLISTED`.
- `algorithm.mode == "pcs_replication"` switches off the newcomer rule and relaxation (A-list
  only) — a branch + test, so Phase 6/experiments can flip it.

`app/algorithms/reputation.py` — **`newcomer_snapshot()` only** (§9.1.3): Γ⁰, Γ_m⁰=0.5, ω⁰ from
distinct evidence domains, μ=T=0.5, β=`newcomer_review`, then `C` (Eq.4) and `P` (Eq.12) with the
default weights. Pure; the rest of reputation is Phase 6.

`app/algorithms/availability.py` — interval-overlap math (§9.17): `overlaps(a_from,a_to,b_from,
b_to)` (half-open, adjacent intervals **don't** overlap, same-day start/end boundaries tested) and
`is_feasible(existing_confirmed, new_commitment, profile_hours)`.

## Backend — services, repositories, schemas, routes (§10)

- `services/reputation_read.py` — the **only** snapshot read path; returns `C, P, …` + `seeded`
  (D48). Uses `populate_existing` so writes by definers/seed are re-read (Phase 4 lesson #8).
- `services/marketplace.py` — search (`plainto_tsquery`, **whitelisted** filters
  `skills, budget_min/max, deadline_max, team_size, role, hours, sort`; cursor pagination; never
  exposes bid counts/prices, §14.5); recommended (§9.16, cached 5 min per user).
- `services/bids.py` — create/edit/withdraw with state rules (§8: `ACTIVE → WITHDRAWN`; edits only
  while `BIDDING`), bid limits (20/hour, §14.8), one bid per (project, developer), availability
  check on create; `eligibility_preview()` (dry-run, D45) building a `BidInput` from the caller's
  own snapshot; `client_bids()` returning all bids + per-bid `FilterResult` reasons; `too_few()`
  (§9.19) shortfall per slot + offered actions.
- `repositories/bids.py`, `repositories/marketplace.py`, `repositories/reputation.py` — ORM only
  (no raw SQL; forbidden-pattern scanner).
- `services/availability.py` — reservation lifecycle stub for Phase 5 (bids only declare the
  commitment; TENTATIVE/CONFIRMED come with invitations in Phase 8). Overlap feasibility used by
  the filter's `UNAVAILABLE` gate against existing CONFIRMED reservations.
- Routes (`api/v1/marketplace.py`, `api/v1/bids.py`) — contract-first (401/403/404(+422),
  OpenAPI example, summary) per §10.4:
  - `GET /projects/search` · `GET /projects/recommended` (Developer).
  - `GET /public/projects` · `GET /public/projects/{id}` (GUEST, limited columns, no bids).
  - `POST /projects/{id}/bids` · `GET /me/bids` · `PATCH /bids/{id}` · `DELETE /bids/{id}`
    (Developer, own).
  - `POST /projects/{id}/bids/eligibility` (Developer; dry-run; D45).
  - `GET /projects/{id}/bids` (Client own + Admin; all bids + eligibility).
  - `GET /projects/{id}/too-few-bids` + the action endpoints reuse Phase 4
    (`extend-bidding`, slots PUT, `cancel`) + a new `PATCH /projects/{id}/filter-overrides`
    (client P0/C0 overrides, D47).
- Authz policies: `bid.create/read/write`, `marketplace.read`, `reputation.read`; every new route
  added to the **authz matrix** (§14.5) — deny-by-default, foreign object → 404.
- Job: `jobs/bidding_deadline.py` — at `bidding_deadline` move `BIDDING → FORMING` (or notify the
  client) and run the too-few-bids check; registered with the scheduler; frozen-clock tested.
- Notifications: too-few-bids + bidding-closing use the Phase 1 notification service (in-app;
  email outbox for the client).

## Frontend (devsync-ui + frontend-design; mobile-first; all four states; screens 6, 10–12, 23)

- **Find Projects** (screen 10, `/dev/find`): search box, filter controls (skills MultiSelect,
  budget, deadline, team size, hours, sort), results as cards/table with **URL-synced filters**
  (stay across reload + back), cursor "load more". Recommended strip (§9.16). No bid data shown.
- **Project details + bid sheet** (screen 11, `/dev/projects/:id`): project summary, CPM plan
  (reuse the Phase 4 `Gantt`/`CpmTable` read-only), slots, and the **bid sheet** with a **live
  eligibility preview** (debounced `POST …/bids/eligibility`) showing per-constraint pass/fail and
  **"would be filtered out because …"** for an ineligible draft; place / edit / withdraw.
- **My Bids** (screen 12, `/dev/bids`): list with statuses; "why not selected" explanations arrive
  in Phase 7 (placeholder copy now).
- **Client Bids table** (screen 23, `/client/projects/:id/bids`): all bids with C/P/days/price and
  eligibility + reason chips; **too-few-bids banner** with the five actions (D47); slot coverage
  summary (e.g. "React 2/1 ✓").
- **Public project list** (screen 6, `/projects`): extend the Phase 2 public page with real
  search/filter (no bids, GUEST columns).
- `features/marketplace/api.ts` + `features/bids/api.ts` (TanStack Query hooks); filters in the URL
  via search params; new screens added to `e2e/screens.ts` (CSP, axe, responsive 375/768/1440) and
  visual baselines (regenerated and **reviewed**). Reputation values show the dev-only "seeded"
  marker.

## Seed + Demo 1 tooling (§18, §17.0)

- `backend/scripts/seed_data/stage1_reputation.json` — the §18.4 table (9 experienced devs).
- Extend `make seed-demo` (base, §18.1) + add `STAGE=1`: admin, Rahim (payment verified), 12
  developers (profiles/skills/portfolios/test scores), fixed + newcomer snapshots, the **"Online
  ordering system"** project in `BIDDING` with **12 sealed bids** (see table below), one DRAFT with
  a deliberate cycle, one project with too few bids. Seed script **asserts** the filter result
  counts (drives the gate check).
- `make demo-check DEMO=1` (re-run gates 0–5; `seed-demo STAGE=1`; `e2e/demos/demo-1.spec.ts` on
  chromium/firefox/webkit/mobile ×3; write `runs/demos/demo-1.md` + `.webm`), `make demo-up STAGE=1`
  (prod-style compose, offline), `make demo-reset STAGE=1` (< 30 s), `make demo-preflight` (Docker,
  ports, cert trust, disk, seed integrity). Demo accounts → `runs/demos/accounts-1.txt`
  (**gitignored**).

**Proposed §18.4 bid table (drives the P5 gate check — confirm, Q3).** Budget ৳120,000, deadline
30 days, slots React/FastAPI/PostgreSQL/Testing. **10 eligible, 2 ineligible, different reasons:**
- Ineligible #1 — **Shakib Hasan** (experienced, "often late"), 31 days → `TOO_SLOW` (31 > 30).
- Ineligible #2 — **Lamia Akter** (newcomer, FastAPI evidence 0.75) bids the **PostgreSQL** slot
  with no PostgreSQL evidence → `NO_SKILL_EVIDENCE`.
- Eligible newcomers — **Nadia** (React 0.85) and **Mehjabin** (Testing 0.90) via the newcomer
  rule. (All 3 newcomers bid; 2 pass.)
- The remaining 7 experienced devs fill the slots; all have `P ≥ 0.56 ≥ P0` and `C ≥ 0.40`.

## Security (§14.13 row 5)

RLS on `bids`/`reservations` (sealed in the DB too); sealed-bid authorization in services;
marketplace never leaks bids; bid limits (20/h); availability checks; **search input safety**
(`plainto_tsquery`, whitelisted filters/sorts → 422, tampered cursor → 422). `/security-review` →
`docs/security-reviews/phase-05.md` with 0 unresolved high.

## Tests (B3 minimum + additions; no happy-path-only; each addition's reason noted)

**Algorithm 1 filtering (pure, ≥ 95%):** one test **per reason code**; **equal-to-threshold passes**
at every paper boundary (`P==P0`, `C==C0`, `t==T^d`, `c==C''_j`); newcomer rule (evidence ≥/<
pass_mark; `newcomer_competency_check` on/off); each relaxation step reported (and `TOO_FEW_BIDS`
when still short); advancement ordering per preset (P/C/t/c); shortlist size `K_s`; `pcs_replication`
mode disables newcomer+relaxation. **Property tests:** eligible ⊆ input; relaxation monotone (never
*removes* eligibles); ordering total per `a`. *Added — stable reason precedence* (a bid failing
several gates reports a deterministic first reason; matters for the client UI and the gate's
documented reasons).

**Availability:** overlap at boundaries (adjacent intervals don't overlap; same-day start==end);
feasibility sum vs `profile_hours`. *Added — DB concurrency: two parallel confirmations that would
overlap → exactly one wins* (advisory/row lock; prevents double booking under race).

**Sealed-bid security (every endpoint × every role):** another developer's bid → 404 on GET/PATCH/
DELETE and absent from every list/search/count; a different client → 404 for another client's bids;
GUEST/public pages reveal nothing about bids; **RLS tests run directly as `devsync_app`** on
`bids`/`reservations` (zero rows cross-user); mass assignment (`status, developer_id,
ineligible_reasons, eligibility`) → 422; every new route in the authz matrix.

**Bid rules:** bid after deadline / on non-`BIDDING` project → 409 `INVALID_STATE`; price integer
paisa boundaries; `days_needed` bounds; one bid per (project, developer); edit/withdraw follow the
state machine; rate limit 20/h → 429.

**Search:** injection corpus (tsquery specials, SQL fragments, very long input, Unicode NFC);
filter/sort outside whitelist → 422; tampered/garbage cursor → 422; pagination boundaries (empty,
exact page, last page).

**Jobs (frozen clock):** bidding-deadline transition + notifications; too-few-bids flow; idempotent
re-run (running twice doesn't double-notify or double-transition).

**Contract:** stateful schemathesis flow — create project → publish → bid → edit → withdraw.

**Reputation read:** `newcomer_snapshot()` hand values (§9.1.3); seed assertion recomputes C/P and
matches §18.4; `reputation_read` is the only path (layer test).

**Real-stack E2E** (`e2e/phase5.spec.ts`, chromium + mobile; written early):
- Developer searches/filters; **filters persist in the URL across reload and back**; opens a
  project; bid sheet shows live eligibility incl. **"would be filtered out because …"**; places,
  edits, withdraws a bid.
- **Sealed across contexts:** a second developer in a separate browser context sees nothing of the
  first's bid (list, project page, counts, search, recommended).
- Client sees all bids with eligibility + reasons; the **too-few-bids banner** + actions on the
  short project.
- A **newcomer** (passed skill test → `skill_evidence`) passes the newcomer rule.
- Every new screen: CSP + axe + layout at 375/768/1440.

## Gate (P5 additions)

- `phase5_checks(g)` (chains `phase4_checks`): run the §18.4 seed and assert the **documented
  eligible/ineligible counts and reasons** for "Online ordering system" (10 eligible, Shakib
  `TOO_SLOW`, Lamia `NO_SKILL_EVIDENCE`); run the filtering boundary + newcomer + relaxation tests;
  the sealed-bid RLS test; assert `docs/plans/phase-05.md` + `docs/security-reviews/phase-05.md`
  exist.
- Register `5: phase5_checks`. Gate E2E runs 4 browsers ×3 (demo phase). Coverage thresholds
  (§16.5): backend 85 / frontend 70 / algorithms ≥ 95.
- Run the full gate **detached** (`systemd-run --user … --phase 5 --keep-going`), dev stack stopped
  to free RAM (handoff gotcha; D28).

## Housekeeping (docs + decisions)

`docs/ALGORITHMS.md` (Algorithm 1 plain-English + a worked eligibility example from the seed);
`docs/API.md` Phase 5 endpoints; `docs/FR_MAPPING.md` (FR-BID/FR-SRCH rows); `docs/SECURITY.md`
Controls (Phase 5) row; `docs/PAPER_ALIGNMENT.md` note (Algorithm 1 = exact with A-list);
`DECISIONS.md` D44–D48; `PROGRESS.md`; `docs/BACKLOG.md` statuses; `docs/sprints/` entry.

## Verification (before the gate)

Fast loop on this laptop (D28): `tsc -b`, eslint, prettier, vitest; backend `pytest -m "unit or
api"` + the filtering/availability unit tests; `check_forbidden/layers/rls/openapi`; migration
up/down/drift. Then the detached full gate; `phase5.spec.ts` (chromium) against the test stack.

## Risks

- **Seed fidelity drives the gate** — the bid table must produce exactly the documented
  FilterResult; the seed asserts it, and the filtering unit tests pin each reason independently.
- **Sealed-bid leaks** are the headline risk — defence in depth (authz 404 + RLS + role-specific
  response models + search never selecting bid columns) and cross-context E2E.
- **Demo tooling is large** — `demo-check`/`demo-up`/`demo-reset`/`demo-preflight` +
  `demo-1.spec.ts` are new; budget time, and if Demo 1 is at risk, **recommended projects** (§9.16)
  may move to Demo 2 (§17.0) — **sealed bidding and Algorithm 1 never move**.
- **E2E flakiness on the 5.6 GB laptop (D28)** — develop with the chromium spec; the 4-browser ×3
  gate run may need Taeen's machine (same as Phase 4).

## Resolved decisions (confirmed by Salwa, 2026-10-20)

1. **Shortlist size (D46):** per-slot `K_s = max(3·count_s, 6)` (§9.2) — the algorithm text; it
   feeds the Phase 7 PSO.
2. **Eligibility dry-run (D45):** `POST /projects/{id}/bids/eligibility` (developer, not persisted).
3. **Seed bid table (§18.4):** 10 eligible; 2 ineligible — **Shakib `TOO_SLOW`** (31 d) and
   **Lamia `NO_SKILL_EVIDENCE`** (newcomer bids PostgreSQL without evidence); eligible newcomers
   Nadia + Mehjabin. The seed asserts this; it is the P5 gate check.
4. **Too-few-bids (D47):** "lower standards" stores client P0/C0 overrides, "reduce team" edits
   slots while `BIDDING`; both reflect immediately in the eligibility preview. Formation (Phase 7)
   consumes the overrides.
