# Start prompt for Salwa's Claude Code (Phases 4–5)

Paste everything below the line into Claude Code, opened in the repository root, as the first
message of the first session. Turn Plan Mode on first (Shift+Tab until "plan mode on").

---

You are taking over the DevSync project from another team member's Claude Code. I'm Salwa Baki,
the backend developer. I own **Phase 4 (projects and the CPM planner)** and **Phase 5
(marketplace, sealed bidding, Algorithm 1 filtering)**. Mashfikuzzaman Taeen (team leader)
built Phases 0–3. Every gate passed, and the work stopped exactly at git tag `phase-3`.
**Demo 1 is Monday 2 November 2026** and covers Phases 0–5, so Phase 5 ends with the Demo 1
readiness check.

Don't write any code yet. Your first job is to **build a complete, accurate understanding of
the project and the repository**, then report back, so that Phase 4 continues smoothly from where
Phase 3 ended. Work through the steps below in order. Read files yourself. Don't skim, and don't
guess. Where something is ambiguous or contradictory, list it as a question for me.

## Step 1 — The rules of this project

Read these completely, in this order:

1. `CLAUDE.md`, the working rules. Follow them exactly for the whole project, including the
   session start and end routine.
2. `DEVSYNC_BUILD_SPEC.md` **§0 and §1 in full**: how to use the spec, the Plan Mode workflow,
   the working rules, skills, hand-offs and the product summary. This spec is the single source
   of truth. Never edit it, except to fix an agreed mistake recorded in `DECISIONS.md`.
3. `docs/handoffs/handoff-01-taeen-to-salwa.md`: what exists, gotchas, the dependencies you must
   not break, and how to run everything. Treat its "Gotchas" section as hard-won lessons.
4. `PROGRESS.md`: current state, phase table, gate log, known issues and session log.
5. `DECISIONS.md` **in full (D1–D37)**. Every entry is a binding decision; don't undo any of them
   without asking me. The next new decision is **D38**.
6. `docs/OWNERSHIP.md`.

## Step 2 — The research the product is built on

DevSync implements the paper Akter et al., 2023 ("PCS"): `docs/papers/akter2023-pcs.pdf`.

- Read the whole paper once for the idea: reputation (Eq. 1–12), worker filtering
  (Algorithm 1), fitness and binary PSO team formation (Eq. 13–19, Algorithm 2), and the payment
  policy (Eq. 20–23).
- Then read **spec §9 completely**. §9 is authoritative for every formula; the PDF is only for
  checking wording and notation.
- Pay special attention to:
  - §9.0, the conventions and the resolved ambiguities A1–A13;
  - §9.1.3, newcomer starting values;
  - §9.2, Algorithm 1 plus the newcomer rule;
  - §9.10, CPM and forecasting;
  - §9.16, recommended projects;
  - §9.17, availability reservations;
  - §9.19, too few bids.
- If the paper and §9 disagree, follow §9 and record the mismatch in `DECISIONS.md`. Never
  change a formula silently.

## Step 3 — Your two phases and everything they reference

Read spec **§17.0** (demo schedule, Demo 1 walkthrough, demo readiness check, demo-day
environment, what may move if a demo is at risk). Then read **§17 "Phase 4" and "Phase 5"**
word for word, and then every section they reference, in full:

- **Data model:** §7 overall, with §7.3 (projects and planning), §7.4 (bids, reservations) and
  §7.7 (`reputation_snapshots`).
- **State machines:** §8, especially Project, Milestone and Bid.
- **API:** §10.1 conventions and §10.2 (Projects, Marketplace, Bids, and the public endpoints).
- **Jobs:** §11, the bidding-deadline job and the too-few-bids flow.
- **Notifications:** §12, for the too-few-bids notifications.
- **UI:** §13.5 screens 6, 10, 11, 12, 21, 22, 23 and 31; §13.8 (quality bar); §13.9 (Demo 1
  layouts); §13.14 (responsive).
- **Security:**
  - §14.5 (authorization, sealed bids) and §14.7 (validation, injection; search is a target);
  - §14.13 **rows 4 and 5** (the controls your phases must implement and test);
  - §14.15 (RLS).
- **Testing:** §16.4 (mandatory security tests, which only grow), §16.5 (the gate), §16.6
  (Makefile targets you must add).
- **Seed data:** §18 (§18.2, the "Online ordering system" plan the Phase 4 gate checks; §18.4,
  the stage-1 seed and reputation values the Phase 5 gate checks).

## Step 4 — Study the repository in depth

Understand the code before you plan. Read the actual files, not just their names.

**Backend (`backend/`)**
- `app/main.py` (router registration, middleware order) and `app/core/middleware.py`
  (including the upload body limit).
- `app/core/`:
  - `authz.py`: how policies are registered; the 401/403/404 semantics; Phase 3 policies as the
    pattern.
  - `errors.py`: domain errors and the envelope; `InvalidStateTransition` → 409.
  - `money.py`: integer paisa and Decimal rules. Budgets and bids depend on it.
  - `clock.py`, `audit.py`, `ratelimit.py` and the `rate_limit(...)` dependency in
    `app/api/deps.py`.
- `app/api/deps.py`: `require(...)`, `acting(...)` (returns the service `Ctx`), `rate_limit(...)`.
- `app/db/context.py` and `app/db/session.py`: how the RLS context (`app.user_id`, `app.role`)
  is set per transaction; web role vs worker role.
- `app/db/rls_exempt.yml`.
- `alembic/versions/0002_identity_rls.py`: the RLS helper functions (`app_uid()`, `app_role()`,
  `is_admin()`, `is_system()`) and the definer pattern.
- **`alembic/versions/0004_profiles_files_tests.py` in full.** It is the reference for how a
  Phase 3+ migration is written:
  - tables and owner policies;
  - SECURITY DEFINER functions with a pinned `search_path`, and grants;
  - `caller_is_system()` (D36);
  - guard triggers (D35);
  - seed data from a frozen JSON file;
  - a downgrade that drops everything.
- The full Phase 3 vertical slice, as the pattern to copy:
  - models: `app/models/profiles.py`;
  - repositories: `app/repositories/profiles.py`, `skill_tests.py`;
  - schemas: `app/schemas/profiles.py`, `skill_tests.py` (`StrictRequest` rejects unknown
    fields);
  - services: `app/services/profiles.py`, `skill_tests.py`, `files.py`, `context.py`;
  - routes: `app/api/v1/profiles.py`, `skill_tests.py`, `files.py` (OpenAPI examples, declared
    error responses, rate limits).
- `app/services/skill_tests.py` and the `skill_evidence` table: the **newcomer rule in Phase 5
  reads this verified evidence**.
- `app/algorithms/`: currently empty apart from `__init__`. Phase 4 adds `cpm.py` and
  `forecast.py`; Phase 5 adds `filtering.py` and `reputation.py` (only `newcomer_snapshot()`).
  This layer must stay **pure** (`scripts/check_layers.py`).
- `app/jobs/` (scheduler, worker, `profile_jobs.py` as the pattern) and `app/api/v1/test_seed.py`
  (test-only seeding; test environment only).

**Scripts and gate**
- `backend/scripts/phase_gate.py` in full: all 20 steps, `coverage_thresholds` (Phase 4–9:
  backend 85%, frontend 70%), `CRITICAL_MODULES` (`app/algorithms/` must be ≥ 95%),
  `DEMO_PHASES`, the `if g.phase >= 4` perf step, and `phase2_checks` / `phase3_checks`.
  **You must add `phase4_checks` and `phase5_checks`.**
- `check_openapi.py` (`PUBLIC_OPERATIONS`, required examples and responses), `check_layers.py`,
  `check_rls.py`, `check_forbidden.py`.
- `Makefile`: which targets exist and which still print "arrive in later phases" (`seed-demo`,
  `erd`, `demo-check`, `demo-up`, `demo-reset`, `demo-preflight`, …).

**Tests (`backend/tests/`)**
- `conftest.py` and `helpers.py` (the `Api` client, `sign_in_as`, stack fixtures).
- `tests/security/test_authz_matrix.py`: every route must have an entry.
- `tests/integration/test_rls_profiles.py`: the RLS-per-table pattern.
- `tests/security/test_profiles_files.py`, `test_skill_tests.py`: API, IDOR, mass assignment,
  lifecycle.
- `tests/api/test_schemathesis.py`: Phase 5 adds a **stateful** schemathesis flow.
- `tests/unit/test_uploads.py`: unit-test density expected for security-critical code.

**Frontend (`frontend/`)**
- `.claude/skills/devsync-ui/SKILL.md` and `references/components.md`. Load the `devsync-ui`
  and `frontend-design` skills before any screen work; `devsync-ui` wins where they disagree.
- `src/design/*` (tokens, `motion.ts` and its lint rule), `src/components/ui/*` (reuse; don't
  re-invent), `src/components/shell/*`.
- `src/app/router.tsx`, `navigation.ts` (entries with `phase: 4/5` are coming-soon placeholders
  you will replace), `guards.tsx`, `queryClient.ts`.
- `src/api/client.ts` (`api()`, `upload()`, `fileUrl()`, CSRF handling) and `src/api/types.ts`.
- The Phase 3 screens as the pattern for data hooks, forms, the four states and tests:
  `src/features/profile/*` (`api.ts`, `schemas.ts`, `ProfilePage.tsx`, `PortfolioCard.tsx`,
  `profile.test.tsx`) and `src/features/challenges/*`.
- `src/lib/format.ts` (`formatMoney(paisa)`, dates in Asia/Dhaka, scores).
- E2E: `e2e/test.ts`, `fixtures.ts`, `screens.ts`, `layout-checks.ts`, `csp.spec.ts`,
  `a11y.spec.ts`, `responsive.spec.ts`, `visual.spec.ts`, `phase3.spec.ts`;
  `playwright.config.ts` (projects chromium, firefox, webkit and mobile are used by the
  Phase 5 demo gate).

**Infrastructure**
- `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.test.yml`, `infra/nginx/`
  (CSP; upload and `internal` locations).

**Earlier phases' records**
- `docs/plans/phase-00.md` … `phase-03.md` and `docs/security-reviews/phase-00.md` …
  `phase-03.md`: the expected depth of a plan and a security review.
- `docs/API.md`, `docs/SECURITY.md`, `docs/TESTING.md`: you extend these each phase.

## Step 5 — Verify the starting point on this laptop

Follow the session-start routine in `CLAUDE.md` and section 2 of the hand-off:

1. `git pull`, `make env` (my own secrets), `make certs`, `make up`, `make migrate`,
   `make create-admin`.
2. Open https://localhost and Mailpit (http://127.0.0.1:8025).
3. Run `make gate PHASE=3`. It must print `PHASE 3 GATE: PASS` on this laptop before Phase 4
   starts. Run it detached with `systemd-run --user` as shown in the hand-off's gotchas. If
   anything fails, diagnose and tell me; don't "fix" it by weakening a test, threshold, lint
   rule or security default (`CLAUDE.md` non-negotiables).

## Step 6 — Report back before planning

Give me a concise report:

1. The product in your own words, and where Phases 4–5 sit in it.
2. What Phases 0–3 built: the main modules, tables, endpoints and screens you will build on.
3. The conventions you will follow:
   - layers;
   - RLS and definers;
   - authz and the matrix;
   - OpenAPI contract rules;
   - money in paisa;
   - the pure `algorithms/` layer;
   - frontend patterns and skills;
   - test layers;
   - the gate.
4. Exactly what the Phase 4 and Phase 5 gates will require. That includes the `phase4_checks`
   and `phase5_checks` to add, the perf budget, coverage thresholds, the demo-phase browser
   matrix, `make demo-check DEMO=1`, and the stage-1 seed.
5. Risks and open questions, especially:
   - ambiguities between §7, §9, §10 and §17;
   - how the seeded reputation values (§18.4) flow through `services/reputation_read.py`;
   - the timeline to Demo 1.
6. The result of `make gate PHASE=3` on this laptop.

Then, **in Plan Mode**, write the Phase 4 plan to `docs/plans/phase-04.md`. Use the structure and
depth of `docs/plans/phase-03.md`, and list the skills you loaded. Present a short summary and
**wait for my approval** before building.

## Rules that apply throughout (from `CLAUDE.md` and spec §0.2)

- **Phase order is strict.**
  - Plan Mode → approved plan → build → `/security-review` → `docs/security-reviews/phase-NN.md`.
  - `make gate PHASE=N` must print `PHASE N GATE: PASS`.
  - Update `PROGRESS.md`, commit `phase-N: <summary>`, tag `phase-N`, push.
  - Stop and report.
- **Security in every phase:** fail closed, deny by default. Tests cover invalid input,
  boundaries, permission failures and IDOR, never only the happy path. Sealed bids must be
  invisible to other developers through **every** endpoint and role.
- **Paper formulas exactly as §9.** Ambiguities go through documented, configurable defaults.
- **Money is integer paisa** with `Decimal` maths in `app/core/money.py`; never floats,
  including in the frontend.
- **Times** are stored in UTC and shown in Asia/Dhaka. Never log secrets.
- **Dependencies:** a new one only if the spec names it or a `DECISIONS.md` entry records it;
  pinned exactly and at least 14 days old.
- **Ask, don't guess.** Record every decision and deviation in `DECISIONS.md` from D38 onwards.
- **End every session** by committing work in progress to the phase branch and updating
  `PROGRESS.md` (session log and current state).
- **Never store the GitHub token** in git config or files; it is passed per command.
- **Taeen stays available** for questions about Phases 0–3.
