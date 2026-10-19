# Phase 4 — Projects and the CPM planner (plan)

## Context
Phases 0–3 are done (gates PASS, tags `phase-0..3`, pushed); hand-off 01 moved ownership of
Phases 4–5 to Salwa Baki. Phase 4 (spec §17 "Phase 4") lets clients author complete project
plans — information, requirements, skill slots, milestones with durations/shares/skills, and
finish-to-start dependencies — and see a **correct, beautiful CPM timeline** (earliest/latest
dates, slack, all critical paths, forecast). It is the **Plan** stage of the core loop and the
foundation Phase 5's bidding and Phase 6+'s formation/monitoring build on. Phase 5 (marketplace,
sealed bids, Algorithm 1) follows and closes **Demo 1 (Mon 2 Nov 2026)**. Outcome:
`make gate PHASE=4` → `PHASE 4 GATE: PASS`; commit `phase-4: …`, tag `phase-4`, push.

**Read:** §7.3 (projects/planning), §8 (Project, Milestone, Bid states), §9.10 (CPM & forecast),
§10.1–10.2 (Projects endpoints), §13.5 screens 21–22, 31 (+ 20 client dashboard tie-ins),
§13.8–13.9, §13.14, §14.5, §14.7, §14.13 **row 4**, §14.15 (RLS policy table), §16.4–16.6,
§17.0, §18.2 (golden CPM). **Skills loaded:** `devsync-ui` + `frontend-design` for every screen
(devsync-ui wins on conflicts); no `threejs-*` (no 3D in Phase 4).

## Dependencies
**None new.** CPM/forecast use the standard library only (own Kahn topological sort + DFS cycle
finder; no NetworkX yet — it arrives for collusion graphs in Phase 11). Gantt and the dependency
graph are **custom SVG** components (spec §3: "no external lib"). Any deviation → DECISIONS.

## Decisions to record (D38 onwards)
- **D38 · Enum strategy.** Create the full `project_status` (DRAFT, BIDDING, FORMING,
  TEAM_PENDING, IN_PROGRESS, ON_HOLD, REVIEW_WINDOW, COMPLETED, CANCELLED) and `milestone_status`
  (PLANNED, FUNDED, ACTIVE, SUBMITTED, APPROVED, CHANGES_REQUESTED, AUTO_APPROVED, PAID, DISPUTED,
  REFUNDED) enums now (§8), even though Phase 4 only drives DRAFT↔edit, DRAFT→BIDDING,
  BIDDING→BIDDING (extend), →CANCELLED. Reason: `ALTER TYPE ADD VALUE` cannot run inside a
  transaction and churns later migrations; defining the full §8 alphabet once is cleaner and the
  service still rejects every transition not yet implemented (`InvalidStateTransition` → 409).
- **D39 (decided) · Payment-method verification for publish.** §8's DRAFT→BIDDING guard needs
  "payment method verified" (`users.payment_verified_at`); satisfied by a simulated
  `POST /me/payment-method/verify` (CLIENT, idempotent), shown in the wizard's publish step.
  (To be sanity-checked with Taeen per the hand-off; recorded as D39.)
- **D40 · CPM-over-deadline is a warning, not a block.** DRAFT→BIDDING is allowed when CPM
  duration > `deadline_days` only if the client acknowledges the warning (`publish` body carries
  `acknowledge_schedule_risk: true`); the warning is surfaced in step 6 of the wizard (§13.5
  screen 21). Matches §8 ("CPM duration ≤ deadline **or client acknowledged warning**").

## Database — migration `0005_projects_planning`
Written in the `0004` style: `op.create_table` per table → enums → `GUARDS`/definer functions →
RLS `_policies()` loop (ENABLE + FORCE + `migrator_all` + role policies) → grants → indexes →
`downgrade()` that drops everything (verified upgrade→downgrade→upgrade + `alembic check`).
Autogenerate inside the backend image (hand-off gotcha), then add RLS/definers by hand.

- **Tables (§7.3):**
  - `projects` — client_id, title(5–120), summary(≤300), description(≤10000),
    requirements(≤5000), budget_paisa (BIGINT ≥0), bonus_pool_paisa (≥0), deadline_days (1–365),
    start_date, bidding_deadline, team_size (2–10), status `project_status`, cancel_reason,
    cancelled_at, completed_at, repo_url, settings_version, current_baseline_id, acknowledged
    flags, version (optimistic concurrency). `payment_verified` read from `users`.
  - `project_slots` — project_id, skill_id, label, count (≥1). Service enforces Σ count =
    team_size.
  - `milestones` — project_id, name, description, duration_days (≥1), share_bp (0–10000),
    position, status `milestone_status` (PLANNED at creation), actual_start/finish,
    revision_count, submitted_at/approved_at/auto_approve_at. Service + **publish-time DB trigger**
    assert Σ share_bp = 10000.
  - `milestone_skills` — milestone_id, skill_id.
  - `milestone_dependencies` — project_id, predecessor_id, successor_id; UNIQUE(pred, succ),
    CHECK(pred ≠ succ) (no self-loop); **acyclicity enforced in the service** (CPM validate).
  - `plan_baselines` — project_id, version, cpm jsonb, reason, created_by, approved_by_client,
    approved_by_lead; immutable once approved (guard trigger). First baseline written at publish.
  - `plan_change_requests` — project_id, proposed_by, changes jsonb, status
    (PENDING/APPROVED/REJECTED). Table + model now; the approve/reject flow is a thin stub until
    a team exists (full re-planning is Phase 8/9) — created now so the table/relationships are
    stable; only client-side create is wired, clearly marked.
- **RLS (§14.15):** helper functions `is_project_client(project_id)` (STABLE, pinned
  search_path) created here; later phases add `is_project_member`/`is_participant`. Policies:
  `projects`, `project_slots`, `milestones`, `milestone_skills`, `milestone_dependencies` —
  SELECT when `status <> 'DRAFT'` (any role, incl. GUEST through the **`public_projects`** view
  with limited columns) **or** `is_project_client()` **or** `is_admin()`; INSERT/UPDATE/DELETE
  only `is_project_client()` (+ migrator). `plan_baselines`/`plan_change_requests` — client of
  the project or admin; baselines are SYSTEM/owner-insert, never updated (append-only via
  trigger). No table is RLS-exempt (none is a public catalogue). Draft projects are invisible to
  everyone but their client and admins — tested per table as `devsync_app` with a foreign context.
- **Public view/definer:** `public_projects` exposes only id, title, summary, budget range, team
  size, skills, deadline, bidding_deadline, status for non-DRAFT projects (screen 6 / Phase 5
  marketplace reads it). Never exposes description, requirements, client PII beyond display name.
  (GIN full-text search vector + index are added in **Phase 5** with search, per §7.9/§17 Phase 5.)
- **Indexes (§7.9):** `projects(status, bidding_deadline)`, `project_slots(project_id)`,
  `milestones(project_id, position)`, `milestone_dependencies(project_id)`, FK indexes.

## Backend — algorithms (PURE, ≥ 95% coverage, `check_layers` clean)
- `app/algorithms/cpm.py` — dataclasses `MilestoneInput(id, duration_days, share_bp, predecessors)`
  and `CpmResult(nodes{ES,EF,LS,LF,slack,critical}, duration, critical_paths, cycle?)`. Steps
  exactly per §9.10: (1) Kahn topological sort; on failure, a DFS returns the cycle as an ordered
  list of milestone names/ids; (2) forward pass ES=max(EF preds,0), EF=ES+dur; (3) backward pass
  LF=min(LS succs) or project duration D, LS=LF−dur, slack=LS−ES, critical ⇔ slack=0; **report all
  critical paths**; (4) calendar dates = start_date + day offsets. Deterministic, no clock.
- `app/algorithms/forecast.py` — §9.10 step 5: per-milestone forecast from (status, progress p,
  elapsed e) with the stated cases (DONE → actual finish; ACTIVE p∈(0,1); ACTIVE p=0; not
  started; late predecessors); forecast project finish = max forecast EF; deadline impact =
  forecast finish − baseline D. Milestone progress p = Σ(estimate × status-weight)/Σ estimate
  (TODO 0, IN_PROGRESS 0.5, REVIEW 0.85, DONE 1) — pure helper, fed synthetic task inputs now
  (tasks arrive Phase 9). **Perf:** 300 milestones < 50 ms (`-m perf`).

## Backend — services, repositories, schemas, routes (§10)
- `repositories/projects.py` — queries only (load project + slots + milestones + deps; list
  mine; whole-set replace helpers). `schemas/projects.py` — `StrictRequest` (extra="forbid"),
  bounds from §7.3, money as `_paisa` ints; `CpmPreviewOut`, `PlanOut`, `ProjectOut` with
  `version`.
- `services/projects.py` (takes `Ctx`): draft create; whole-set replace of slots / milestones /
  dependencies with validation (Σ slot counts = team_size; Σ share_bp = 10000; ≤ 300 milestones;
  duration ≥ 1; finish-to-start only; cycle rejected with the offending cycle); **plan preview**
  (runs CPM without saving, cached per plan version in Redis); **publish** with the §8 guards
  (valid plan, ≥ 1 slot, payment verified [D39], CPM ≤ deadline or acknowledged [D40]) →
  DRAFT→BIDDING, writes baseline v1; **extend-bidding** (max 2, BIDDING→BIDDING); **cancel**
  (before IN_PROGRESS: free, no escrow; sets CANCELLED + reason). State moves only through the
  transition table (`InvalidStateTransition` → 409 `INVALID_STATE`). Every transition audits.
- `api/v1/projects.py` — `POST /projects` (DRAFT); `GET /projects?mine=1`;
  `GET/PATCH/DELETE /projects/{id}` (DELETE only DRAFT); `PUT /projects/{id}/slots|milestones|
  dependencies` (DRAFT only); `POST /projects/{id}/plan/preview`; `POST /projects/{id}/publish|
  extend-bidding|cancel`; `GET /projects/{id}/plan` (baseline + forecast + critical paths; client/
  members/admin). Each: `acting("<policy>")`, declared 401/403/404(+422/409), an example per
  response (URLs as `null`), rate limits (reuse existing scopes; add `project_write` to settings
  if needed → note in DECISIONS). Regenerate `docs/api/openapi.json` + `schema.d.ts`.
- **Authz policies** (`core/authz.py`): `project.create` (CLIENT), `project.read`/`project.write`
  (client owns the resource → else 404), `project.publish`/`project.cancel` (owner). Ownership via
  the resource's `client_id`, mirroring the Phase 3 `session.manage`/`test.take` pattern.
- **ERD (§17.0):** `scripts/gen_erd.py` + `make erd` → `docs/design/erd.svg` from the SQLAlchemy
  models (Graphviz via `sqlalchemy` metadata → DOT → SVG with the system `dot`, or a dependency-
  free SVG writer if `dot` is absent; decide and note). Pre-demo deliverable.

## Frontend (devsync-ui + frontend-design; mobile-first; all four states)
- **Create Project wizard** `/client/projects/new` (screen 21): 6 steps — (1) Information
  (2) Requirements + start date (3) Skills & team (slots: skill + count, team size auto-sums)
  (4) Milestones & dependencies (table editor; "after" chips; live `DependencyGraph`; share-total
  meter must reach 100%) (5) Budget & deadline (budget ৳, bonus-pool toggle + %, platform fee
  shown, deadline days, bidding deadline) (6) Review & generate plan → CPM result (Gantt +
  critical path + table + warnings: cycle, shares ≠ 100%, duration > deadline). Draft **autosaves**
  (PATCH + whole-set PUTs); unsaved-changes prompt; "Publish for bids" requires payment verified.
- **`Gantt`** and **`DependencyGraph`** composites (custom SVG): keyboard-focusable bars/nodes,
  tooltips, table toggle, zoom; critical path styled distinctly (colour **and** icon/label — not
  colour alone, §13.6); today line for in-progress plans.
- **CPM table** (ES/EF/LS/LF/slack/critical) with the same data as the chart.
- **Project plan** `/client/projects/:id/plan` (screen 22): DependencyGraph + Gantt + CPMTable;
  baseline-vs-forecast toggle appears once in progress (later phases); plan-change-request stub.
- **My Projects** `/client/projects` (screen 20 list part): status, progress, risk chips
  (placeholders until monitoring), "Create project" primary action; **cancellation dialog** (type
  the project title to confirm, like delete-account).
- Wire the `phase:4` nav entries in `navigation.ts` to real routes in `router.tsx` (replace
  coming-soon). Add new screens to `e2e/screens.ts` (CSP/axe/responsive) and `e2e/visual.spec.ts`;
  regenerate baselines with `make visual-update` and **look at them**.
- Data hooks in `features/projects/api.ts`; RHF + Zod schemas mirroring the backend;
  `formatMoney`/`formatDays`/dates in Asia/Dhaka from `lib/format.ts`. New components:
  `Gantt`, `DependencyGraph`, `CpmTable`, `Stepper`/`WizardShell`, `ShareMeter` (reuse `ui/*`,
  `PageHeader`, `EmptyState`, `toast`).

## Security (§14.13 row 4)
RLS on every project table (+ cross-user denial tests calling the repository directly as
`devsync_app`); project/milestone validation bounds (title/summary/description/requirements
lengths, budget ≥ min, team_size 2–10, deadline 1–365, duration ≥ 1, share_bp 0–10000);
**plan size limit** (≤ 300 milestones, ≤ team-size slots summing correctly); ownership authz
(foreign project → 404, never 403/leak); **cancellation rules** (only the owner, only before
IN_PROGRESS, free); editing/PUTs rejected after publish (409 `INVALID_STATE`); mass assignment
(`status`, `client_id`, `current_baseline_id`, `settings_version`, `cancelled_at` → 422);
injection-safe (requirements/title free text stored as text, never interpolated; `text()` raw
SQL only in `alembic/`); draft projects never leak through `public_projects` or any list.

## Tests (no happy-path-only)
- **Unit — `cpm.py`:** ≥ 6 hand-calculated textbook cases incl. the §18.2 golden plan, multiple
  critical paths, single milestone, parallel branches, long chains; **cycle detection returns the
  cycle in order**; dates from start_date. **`forecast.py`:** DONE, ACTIVE p>0, ACTIVE p=0, not
  started, late predecessors; deadline impact.
- **Property (hypothesis):** random acyclic DAGs → no milestone starts before its predecessors
  finish; slack ≥ 0 for all; at least one critical path; forward/backward passes agree on
  duration. Random graphs with an inserted back-edge → cycle reported.
- **Perf (`-m perf`):** 300 milestones < 50 ms (CPM) — the gate's step 16 runs this from Phase 4.
- **Integration/RLS:** each new table cross-user (foreign client sees nothing; GUEST sees only
  `public_projects` with limited columns; draft invisible); baseline immutability trigger.
- **API/security:** shares ≠ 100% → 422; > 300 milestones → 422; slot counts ≠ team_size → 422;
  cycle → 422 with the cycle; edit after publish → 409; publish without payment verification →
  409/422 (per D39); foreign project → 404; cancel after IN_PROGRESS → 409; mass assignment;
  authz matrix row per route; schemathesis on all new operations (stateful flow is added in
  Phase 5).
- **Frontend:** wizard step validation + autosave + unsaved-changes prompt; `Gantt` and
  `DependencyGraph` keyboard navigation and table toggle; share meter; CPM table; empty/loading/
  error states; axe.
- **E2E (Chromium + mobile):** create the 6-milestone "Online ordering system" via the wizard →
  see the critical path highlighted and Frontend's slack → a circular dependency is rejected with
  the cycle shown → publish (after simulated payment verification) → cancel a draft. Responsive
  matrix + CSP + axe on the new screens; visual baselines (light/dark, 390/1440).

## Gate (P4 additions)
- **Add `phase4_checks(g)` to `scripts/phase_gate.py`** (chaining `phase3_checks`) and register it
  in the `checks` dict. It: runs the golden CPM test(s) asserting the §18.2 "Online ordering
  system" values (duration 24; critical path Requirements→Database→Backend API→Integration→
  Testing with ES/EF 0/4, 4/9, 9/17, 17/20, 20/24; Frontend ES 4/EF 13/LS 8/LF 17/slack 4); the
  cycle-detection test; and checks `docs/plans/phase-04.md` exists (and lists skills). Returns a
  one-line notes string like the others.
- **Perf step** (already `g.phase >= 4`) now runs `pytest -m perf`; the CPM budget must pass.
- **Coverage** rises automatically to backend 85% / frontend 70% (`coverage_thresholds`);
  `app/algorithms/` is already in `CRITICAL_MODULES` (≥ 95%) — `cpm.py`/`forecast.py` must meet it.
- New screens join the responsive/axe/visual steps; `make erd` produces `docs/design/erd.svg`.

## Housekeeping
Work on branch `phase-4` (new deps: none; if a rate-limit scope is added, DECISIONS entry).
Record D38/D40 (and D39 once Salwa decides). Update `docs/API.md` (Phase 4 endpoints),
`docs/SECURITY.md` (row 4 controls), `docs/TESTING.md`, `docs/ALGORITHMS.md` (CPM in plain English
with the §18.2 worked example), `docs/FR_MAPPING.md` (project/plan FRs). `/security-review` →
`docs/security-reviews/phase-04.md` (0 unresolved high). Update `PROGRESS.md` (current state,
session log, gate table). Commit `phase-4: projects and the CPM planner`, tag `phase-4`, push
(token per command, `refs/heads` + `refs/tags`).

## Verification
`make gate PHASE=4` prints `PHASE 4 GATE: PASS` (detached via `systemd-run --user`, hand-off
gotcha). Manual (§17 Phase 4): create the "Online ordering system" sample plan (§18.2) in the
wizard and confirm the Gantt matches the CPM table; insert a cycle and see it rejected.

## Risks
- **CPM correctness** is the crux — the golden §18.2 values and "all critical paths" must be exact;
  mitigated by hand-calculated fixtures + property tests + the gate golden check.
- **Custom SVG Gantt/DependencyGraph** accessibility and responsive behaviour (keyboard, zoom,
  mobile) — budget time; reuse devsync-ui patterns.
- **Publish payment-verification** (D39) is unresolved — blocks the publish guard until decided.
- **Timeline to Demo 1** (2 Nov): Phase 4 + Phase 5 + readiness in ~2 weeks; keep the wizard's
  demo path (screen 21 → 22) polished first (§17.0 "what earns marks first").
