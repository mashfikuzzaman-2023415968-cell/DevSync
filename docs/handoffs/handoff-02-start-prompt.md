# Start prompt for Raisa's Claude Code (Phases 6–7)

Paste everything below the line into Claude Code as the first message of the first session.
Before you paste it:

1. Clone the repository: `git clone https://github.com/mashfikuzzaman-2023415968-cell/DevSync.git`.
   You need read access; ask Taeen if the clone is refused.
2. Open Claude Code in the repository root.
3. Turn Plan Mode on (Shift+Tab until "plan mode on").

The prompt is self-contained: it tells Claude Code how to set up the laptop, what to study, how
to build, how to test the algorithms in depth, and how to stay consistent with Phases 0–5.

---

You are taking over the DevSync project from two other team members' Claude Code sessions. I'm
**Raisa Tabassum**, the frontend developer of a four-person student team. I own the two most
important phases of the project:

- **Phase 6:** the reputation engine and market simulator.
- **Phase 7:** team formation (fitness, binary PSO, exact solver, fairness dial, explanations).

Mashfikuzzaman Taeen (team leader) built Phases 0–3 and the role assessment; Salwa Baki built
Phases 4–5. Phases 0–5 are built, gated and tagged `phase-0` … `phase-5`, and Demo 1 has been
presented. Work stops at `main`, which holds the latest code plus the hand-off documents.
**Demo 2 is Monday 7 December 2026** (the spec's date; confirm it with Taeen) and covers Phases
6–12, so time matters, but correctness matters more: these two phases are the research core the
viva will examine.

**Don't write any code yet.** Your first job is to understand the project and the repository
completely and accurately, set up and verify this laptop, and report back. Then write the
Phase 6 plan for my approval. Work through the steps below in order. Read the files yourself:
don't skim, and don't guess. Where something is ambiguous or contradictory, list it as a
question for me.

## Step 0 — Set up this laptop

Check what's installed first and tell me what is missing before installing anything system-wide.

- **OS: native Linux (Ubuntu or similar) with a real GPU** exposed at `/dev/dri`, preferably
  Intel or AMD.
  - The gate's performance step measures the homepage 3D scene's frame rate on real hardware
    (DECISIONS D28), so a machine without `/dev/dri` (WSL2, macOS, a VM) **cannot pass the gate**.
  - Development itself works on WSL2 or macOS, but the gate has to run on a Linux laptop with a
    GPU. Check with `ls /dev/dri` and tell me what you find.
- **If this laptop runs Windows,** work inside WSL2. Everything here (`make`, bash scripts,
  `systemd-run`) assumes Linux.
  1. In an administrator PowerShell, run `wsl --install -d Ubuntu-24.04` and restart. Then
     enable systemd: in Ubuntu, put `[boot]` and `systemd=true` in `/etc/wsl.conf`, then run
     `wsl --shutdown` from PowerShell and reopen Ubuntu.
  2. Install Docker one of two ways:
     - Docker Desktop with "Use the WSL 2 based engine" and WSL integration for Ubuntu turned
       on;
     - or Docker Engine inside Ubuntu (Docker's apt repository).

     Check that `docker compose version` works **inside Ubuntu** without sudo.
  3. **Clone inside the Linux filesystem** (`~/DevSync`), never under `/mnt/c/...`. The Windows
     drive is very slow for Docker and Node, and it breaks file permissions.
  4. Before cloning, run `git config --global core.autocrlf input`, so shell scripts keep Linux
     line endings.
  5. Run Claude Code inside Ubuntu, from the repository folder. Open https://localhost in the
     Windows browser; WSL2 forwards localhost.
  6. Give WSL2 enough memory: `%UserProfile%\.wslconfig` with `[wsl2]` and `memory=6GB` or more.
     The gate needs most of 8 GB.

  **The gate on Windows is unproven.** Its performance step needs a GPU device at `/dev/dri`
  inside Linux (D28).
  - Check `ls /dev/dri` in Ubuntu. Some WSL2 setups have one and some don't, and nobody on the
    team has run the gate on WSL2.
  - If it's missing, or step 16 fails there, run the Phase 6 and 7 gates on a native Linux laptop
    instead, such as Taeen's or a Linux USB boot. Develop on Windows and pull the branch there to
    gate it.
  - Tell me which case applies before planning, so the gate is not a surprise at the end.
- **Memory and disk:** about 8 GB RAM and 20 GB free disk space. The first build and the first
  gate download several GB of pinned images (Playwright, Semgrep, Trivy, Postgres), so use a
  good connection.
- **Tools:**
  - Docker Engine 24+ with Compose v2 (`docker compose version`), able to run without sudo;
  - `git`, `make`, Python 3.10+ on the host;
  - `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`);
  - Node 22 LTS with npm. The repository still says Node 20; moving to 22 is the first Phase 6
    task, see Step 6.

**Bring the project up:**

```bash
make env          # creates .env with strong random secrets for this laptop; never commit it
make certs        # dev TLS certificate (mkcert if installed, otherwise openssl, DECISIONS D3)
make up           # dev stack: https://localhost (accept the certificate), Mailpit http://127.0.0.1:8025
make migrate      # migrations 0001–0011 as the migrator role
make create-admin # prints the admin TOTP secret and recovery codes once; I keep them privately
```

- If port 80 is busy, set `HTTP_PORT=8080` in `.env`.
- **Fast local loops for development:**
  - `cd backend && uv venv --python 3.12 .venv && uv pip sync --python .venv/bin/python requirements.lock requirements-dev.lock`,
    then `.venv/bin/pytest -m unit`.
  - `cd frontend && npm ci && npx vitest run`.
- **The offline demo stack:** `DEMO_PASSWORD='<12+ chars>' make demo-up STAGE=1`, then
  `make demo-preflight`.
- **Demo tools:**
  - Phone codes appear at https://localhost/sandbox/sms. Its Quick sign-in tab opens any seeded
    client or developer with one click, never the admin.
  - Emails go to Mailpit.

## Step 1 — The rules of this project

Read these completely, in this order:

1. `CLAUDE.md`, the working rules. Follow them exactly for the whole project, including the
   session start and end routine.
2. `DEVSYNC_BUILD_SPEC.md` §0 and §1 in full: the Plan Mode workflow, the working rules, skills,
   hand-offs and the product summary. This spec is the single source of truth. Never edit it,
   except to fix an agreed mistake recorded in `DECISIONS.md`.
3. `docs/handoffs/handoff-02-taeen-to-raisa.md`: what exists, the honest gate status, known
   issues, what Phases 6–7 depend on and the gotchas. Treat its gotchas as hard-won lessons.
   Then `docs/handoffs/handoff-01-taeen-to-salwa.md` for the older gotchas (migration command,
   SQLAlchemy, MSW, git).
4. `PROGRESS.md`: current state, phase table, gate log, known issues, session log.
5. `DECISIONS.md` **in full (D1–D82)**. Every entry is binding; don't undo any of them without
   asking me. Pay special attention to:
   - D15 (Node), D21 (homepage numbers from a real PSO run), D27 (E2E rate limits);
   - D44, D48 (seeded reputation and the "seeded" marker), D49–D50 (bids, eligibility in a
     SYSTEM session), D51 (dependency security fixes);
   - D53–D54 (cross-browser E2E), D64–D66 (bid verdicts, plain-language reasons, optimistic
     concurrency), D71–D75 (role assessment as newcomer evidence);
   - D79–D82 (gate fixes: CVEs, flaky test, NUL and wrong-type input).

   The next new decision is **D83**.
6. `docs/OWNERSHIP.md`, `docs/BACKLOG.md` (Phase 6–7 rows, including P6-0 and P7-H) and
   `docs/FR_MAPPING.md`.
7. `ROLE_ASSESSMENT_BUILD_SPEC.md` and `docs/ROLE_ASSESSMENT.md`. The role assessment changed
   what "newcomer evidence" means. Filtering, ω⁰ and the fairness dial all depend on it.

## Step 2 — The research the product is built on

DevSync implements Akter et al., 2023 ("PCS"): `docs/papers/akter2023-pcs.pdf`.

- Read the whole paper once for the idea, then **Sections 4.1–4.5 carefully**:
  - reputation, Eq. 1–12;
  - Algorithm 1 (filtering);
  - fitness, Eq. 17–19;
  - binary PSO, Eq. 13–16 and Algorithm 2;
  - complexity.
- Then read **spec §9 completely and slowly**. §9 is authoritative for every formula; the PDF is
  only for checking wording and notation.
  - §9.0: the conventions, the ambiguities A1–A13 with their chosen defaults, and the two
    algorithm modes (`devsync` vs `pcs_replication`).
  - §9.1: every equation, inputs (§9.1.1), newcomer starting values (§9.1.3), communication and
    teamwork ratings (§9.1.4–§9.1.5), evidence events (§9.1.6), outputs and per-skill competency
    (§9.1.7), the change cap.
  - §9.2: Algorithm 1 as already built (`app/algorithms/filtering.py`), whose shortlist feeds
    PSO.
  - §9.3–§9.8: fitness, feasibility, BPSO with the repair operator, exact solver, fairness dial
    and cost of fairness, team comparison, "why this team" and risks, "why not selected" with the
    price counterfactual.
  - §9.9 (team repair, Phase 8, but it reuses your solver with locks) and §9.14 (the trust
    formula Phase 6 needs).
- If the paper and §9 disagree, follow §9 and record the mismatch in `DECISIONS.md`. Never change
  a formula silently.

## Step 3 — Your two phases and everything they reference

Read spec **§17.0** (demo schedule, Demo 2 walkthrough, demo readiness, what may move if a demo
is at risk: team comparison, client analytics and file previews may; the research core never
does). Then read **§17 "Phase 6" and "Phase 7" word for word**, then every section they
reference, in full:

- **Settings:** §6.2. Every `rep.*`, `newcomer.*`, `filter.*`, `pso.*`, `exact.*`, `fairness.*`
  and `fitness.*` key already exists in `backend/app/schemas/platform_settings.py` and the seed
  `backend/alembic/seed/platform_settings_v5.json`, with validation. Reuse them; never hard-code
  a parameter.
- **Data model:** §7.4 (`formation_runs`, `bid_explanations`, `teams`, `team_members`,
  `invitations`) and §7.7 (`reputation_snapshots`, `reputation_skill`, `reputation_log`
  append-only, `reviewer_trust`).
- **State machines:** §8 (run status, bid status, team).
- **API:** §10.1 conventions (errors, Idempotency-Key, long jobs return 202 + `job_id`), §10.2
  (Reputation, Formation, Jobs, admin algorithm endpoints), **§10.3 SSE** (the first SSE endpoint
  in the project is Phase 7's job progress), §10.4 (contract-first).
- **Jobs:** §11 (`formation.run` 60 s, `formation.explanations` 120 s, retries,
  `reputation.recalculate_all`).
- **UI:**
  - §13.5 screens 12 (bid detail: "Why not selected"), 16 (Reputation page) and 24 (Team
    formation);
  - §13.2 (motion; the swarm indicator is the only looping animation);
  - §13.3 (components), §13.8 (quality bar), §13.9 (Demo 2 layouts), §13.12–§13.13 (homepage
    rules), §13.14 (responsive).
- **Security:** §14.13 rows 6 and 7, §14.5 (authz), §14.8 (rate limits and quotas), §14.15
  (RLS).
- **Testing:** §16.1–§16.5 (test layers, determinism, mandatory security tests, the gate step by
  step), §16.6 (Makefile targets).
- **Seed and simulator:** §18.3 (market simulator) and §18.4 (stage seeds; Phase 6 makes
  reputations computed from simulator histories).
- **Experiments:** §19, especially E1 (BPSO vs exact), E2 (runtime), E3 and E6 (fairness), E5
  (reputation tracks true ability). Phase 7's gate runs an E1 smoke test.

## Step 4 — Study the repository in depth

Understand the code before you plan. Read the actual files, not just their names.

**Backend (`backend/`)**
- `app/main.py` (router registration, middleware order); `app/core/` (`authz.py` policies and
  401/403/404 semantics, `errors.py` envelope and codes, `money.py`, `clock.py`, `audit.py`,
  `ratelimit.py`, `idempotency.py`, `json_body.py`).
- `app/api/deps.py` (`require`, `acting`, `rate_limit`), `app/services/context.py` (`Ctx`).
- `app/db/context.py`, `session.py`, `locks.py`, `rls_exempt.yml`; migration `0002` (RLS
  helpers `app_uid()`, `app_role()`, `is_admin()`, `is_system()`), `0004` (definers with pinned
  `search_path`, guard triggers, frozen JSON seeds), `0006`, `0009` (bids, the partial unique
  index), `0011` (role assessment).
- `app/schemas/common.py`: `StrictRequest` rejects unknown fields, NUL characters and wrong JSON
  types (D81–D82). Every request body you add extends it.
- **The algorithm layer, your neighbours:**
  - `app/algorithms/filtering.py` (Algorithm 1, the shortlist PSO receives, `pcs_replication`
    handling);
  - `reputation.py` (`newcomer_snapshot()`; you add Eq. 1–12 here);
  - `availability.py`, `cpm.py`, `forecast.py`, and the role assessment trio.

  Note the style: frozen dataclasses in and out, Decimal at 3 places for stored scores,
  docstrings naming the equation.
- `app/services/reputation_read.py`: **the only read path for reputation.** Phase 5 reads fixed
  seeded snapshots (`seed_data/stage1_reputation.json`) and computes newcomers. Phase 6 replaces
  the values behind it without changing its callers.
- `app/services/bids.py` and `marketplace.py` (how eligibility runs in a SYSTEM session, D50,
  and how reasons are stored on bids, D64), `app/services/role_assessments.py` (newcomer
  evidence), `app/jobs/` (worker, scheduler, how jobs are registered and tested).
- `backend/scripts/seed_demo.py` (stage 1 only so far; Phase 6 adds the computed reputations
  for stage 2), `demo_reset.py`, `seed_data/`.
- **The gate:** `backend/scripts/phase_gate.py` in full.
  - `phase0_checks` … `phase5_checks` chain: each phase's checks call the previous phase's.
  - `CRITICAL_MODULES` includes `app/algorithms/` at ≥ 95%.
  - `DEMO_PHASES = {5, 12, 15}`: Phases 6–7 run E2E on Chromium only.
  - The performance step (16) and the regression guard (19).
  - **You must add `phase6_checks` and `phase7_checks`.**
- Checkers: `check_layers.py`, `check_rls.py`, `check_forbidden.py`, `check_openapi.py`,
  `check_module_tests.py` (every module needs its own tests).

**Tests (`backend/tests/`)**
- `conftest.py`, `helpers.py` (the `Api` client, `sign_in_as`, seeding through the test-only
  router).
- `tests/algorithms/test_filtering.py`, `test_cpm.py`, `test_role_blueprint.py`,
  `test_assessment_scoring.py`: **the expected density and style of algorithm tests**
  (hand-computed fixtures, boundaries, shared vectors).
- `tests/property/`: Hypothesis property tests.
- `tests/security/test_authz_matrix.py` (every route needs an entry), `test_bids.py` (sealed
  bids in every endpoint and role), `test_role_assessment_api.py` (scans every JSON response for
  leaked data).
- `tests/integration/test_rls_*.py` (RLS per table), `tests/api/test_schemathesis.py` (fuzzing,
  deterministic), `tests/perf/`.

**Frontend (`frontend/`)**
- **Skills:** load `.claude/skills/devsync-ui/SKILL.md` (+ `references/components.md`) and
  `.claude/skills/frontend-design/SKILL.md` before any screen work; `devsync-ui` wins where they
  disagree.
- `src/design/*`: tokens (never hard-code colours), `motion.ts` (an ESLint rule rejects numeric
  durations elsewhere), `preferences.tsx` (reduced motion).
- `src/components/ui/*` and `src/components/shell/*`: reuse them, never re-invent. The domain
  composites `Gantt.tsx`, `DependencyGraph.tsx` and `CpmTable.tsx` show how custom SVG charts are
  built accessibly (keyboard focus, tooltips, a "View as table" alternative).
- `src/app/router.tsx`, `navigation.ts` (the "Reputation" `phase: 6` and "Teams" `phase: 7`
  entries are coming-soon placeholders you replace), `features/admin/nav.ts`, `guards.tsx`,
  `queryClient.ts`.
- `src/api/client.ts` (`api()`, CSRF, errors), `src/api/schema.d.ts` (generated from OpenAPI by
  `make openapi`), `src/api/types.ts`, `src/lib/format.ts` (money, dates in Asia/Dhaka, scores
  0–1 shown ×100), `src/lib/redirects.ts` (`pageLoad`).
- **Feature patterns to copy:** `features/bids/*` (how eligibility reasons and "why eligible"
  panels are presented, plain words for developers and the trace for clients, D65),
  `features/projects/*` (wizard, plan page), `features/assessment/*` (a full-screen runner with
  server-driven state), each with its tests.
- **E2E:** `e2e/test.ts`, `fixtures.ts`, `screens.ts`, `stateful-screens.ts` (new screens must be
  listed so axe, the responsive matrix and visual baselines cover them), `layout-checks.ts`,
  `csp.spec.ts`, `phase5.spec.ts`, `demos/demo-1.spec.ts`.

**Records of earlier phases**
- `docs/plans/phase-04.md`, `phase-05.md`, `role-assessment.md`: the expected depth of a plan.
- `docs/security-reviews/phase-04.md`, `phase-05.md`, `role-assessment.md`: the expected depth of
  a security review.
- `docs/ALGORITHMS.md`, `docs/PAPER_ALIGNMENT.md` (Phase 5 rows only so far), `docs/TESTING.md`,
  `docs/SECURITY.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/UI_GUIDE.md`,
  `docs/DEMO_TOOLS.md`.

## Step 5 — Verify the starting point on this laptop (quick, not the full gate)

**Don't run the Phase 5 gate.** It takes 2–3 hours, and Taeen already ran it. Steps 1–12 passed
on the final code, steps 14–19 passed on 2026-11-09, and the one known failure is described in
the hand-off. Your first full gate run is the Phase 6 gate. Instead, check in about 15 minutes
that this laptop works:

1. **Session-start routine** (`CLAUDE.md`): `git pull`, `make up`, `make migrate`.
2. **The app:** open https://localhost and sign in as the admin you created (the TOTP step must
   work). Register a test client and read its phone code at https://localhost/sandbox/sms.
3. **The demo stack:** `DEMO_PASSWORD='<12+ chars>' make demo-up STAGE=1`, then
   `make demo-preflight` (expect `ready (9/9)`). Open the "Online ordering system" as Rahim via
   the Quick sign-in tab and look at its bids and plan. That is the seeded project your Phase 7
   gate will run formation on.
   - The dev and demo stacks use the same containers with different settings and databases, so
     `make demo-up` replaces the dev stack.
   - Afterwards run `make demo-down`, then `make up`, to return to development. Data is kept in
     both databases.
4. **Fast tests:** `cd backend && .venv/bin/pytest -m unit -q`, then
   `cd frontend && npx vitest run`. Both must pass.
5. **GPU:** `ls /dev/dri` shows a `renderD*` device. Without one the gate can't pass, see Step 0.

Report anything that fails. Don't "fix" anything by weakening a test, threshold, lint rule or
security default.

## Step 6 — Report back before planning

Give me a concise report:

1. The product in your own words, and where Phases 6–7 sit in it (plan → **fair team** → work →
   pay → review → **reputation** → the next team is fairer).
2. What Phases 0–5 and the role assessment built that you will build on: tables, services,
   endpoints, screens and settings.
3. The conventions you will follow (layers, pure algorithms, RLS and definers, authz matrix,
   OpenAPI contract, money in paisa, Decimal for scores, `StrictRequest`, frontend skills and
   patterns, the four data states, test layers, the gate).
4. Exactly what the Phase 6 and Phase 7 gates will require:
   - `phase6_checks`: `PAPER_ALIGNMENT.md` lists Eq. 1–12 and a script checks every equation id
     appears in a test name.
   - `phase7_checks`: the seeded project reproduces the expected team for a fixed seed stored in
     a fixture, and an E1 smoke test on 20 instances passes.
   - The performance budgets (reputation, 50-project history, < 20 ms; PSO, |S| = 200 and
     N = 10, < 5 s; exact solver, 18 candidates, < 3 s), coverage (85% / 70%; `app/algorithms/`
     ≥ 95%) and Chromium-only E2E.
5. The result of the quick checks in Step 5 (app, demo stack, fast tests, GPU).
6. Risks and open questions, especially:
   - how the newcomer rule and ω⁰ use role-assessment evidence;
   - how `pcs_replication` must switch off each extension;
   - where reputation inputs come from in Phase 6, given that real reviews and work evidence
     only arrive in Phases 9–11 (answer: simulator-generated histories, §17 Phase 6);
   - the Demo 2 timeline.

Then, **in Plan Mode**, write the Phase 6 plan to `docs/plans/phase-06.md`, using the structure
and depth of `docs/plans/phase-05.md`. List the skills you loaded and the decisions you propose
(from D83). Present a short summary and **wait for my approval** before building. Do the same
for Phase 7 after the Phase 6 gate passes.

**The first task inside Phase 6, before anything else:** backlog item P6-0.
- Move the frontend toolchain and the Nginx build stage from Node 20 to Node 22 LTS (D15).
- Rebuild, run `npx vitest run`, `npm run build` and one E2E smoke test, and record the change
  in `DECISIONS.md`.

## Step 7 — What to build, and how to test it so we know it is right

The spec's §17 lists are the minimum. These phases decide whether the project's research claims
hold, so test them **as an examiner would**: hand-computed values, invariants, comparisons with
an exact answer, and behaviour that makes sense to a person.

### Requirements from other parts of the spec and from decisions (easy to miss)

1. **State machines (§8), using the existing transition-table pattern.** An invalid transition
   is a 409 `INVALID_STATE`, and every transition is audited.
   - Project `BIDDING → FORMING` happens when the client starts formation or the bidding deadline
     passes. This already exists in `services/bidding_terms.py` and the deadline job; reuse it.
   - `FORMING → TEAM_PENDING` happens on confirm.
   - A formation run goes `QUEUED → RUNNING → SUCCEEDED | INFEASIBLE | FAILED | TIMED_OUT`. A timed
     out run returns the best feasible team, if there is one.
   - On confirm, bids become `SELECTED` or `NOT_SELECTED`.
2. **Inputs Phase 5 already decided.**
   - The client's stored P0/C0 overrides from the too-few-bids actions (D47, D54) are a run's
     default thresholds.
   - Bid verdicts are recorded when bidding closes (D64). A bid never records its shortlist rank,
     because that would leak other sealed bids.
   - Reuse `explain_bid()` (D53, pure, in `filtering.py`) for the filter reasons in "why not
     selected"; don't rewrite them.
3. **Paper findings to resolve in Phase 7 (D9 items 1 and 3).**
   - The paper prints Eq. 17's infeasible value as −1. The spec keeps −∞, because a feasible
     fitness can be below −1.
   - The paper initialises positions as U(b_l, b_u). The spec uses Bernoulli(N/k) positions and
     U(b_l, b_u) velocities.
   - Record both as explicit numbered resolutions, after the ones `DECISIONS.md` already uses, and
     give each a named test.
4. **Supervisor questions (§23):** "ask early (Phase 6 at the latest)". Ask Taeen whether they
   have been sent. Record the answers in `DECISIONS.md`. Until then the §9.0 defaults stand.
5. **Notifications (§12).**
   - Phase 7 sends "Team formation finished" (client) and, on confirm, "Not selected" with a link
     to the explanation (each non-selected developer).
   - "Selected (invitation, 48 h)" sits on the Phase 7/8 boundary, and "Reputation updated" on the
     Phase 6/11 boundary. Decide each in the plan and record it.
6. **Jobs (§11).**
   - `formation.run`: 60 s timeout, no retry. `formation.explanations`: 120 s, 1 retry.
     `reputation.recalculate_all`: 30 min, admin only.
   - Test them with RQ's `SimpleWorker` in `tests/jobs/` (`jobs` marker): idempotency, the retry
     count, and a timeout producing `TIMED_OUT`.
7. **The mandatory security list (§16.4) applies to every new route.**
   - Authz matrix and IDOR (another user's run, job or explanation gives 404).
   - Mass assignment: `status`, `seed`, `result`, `is_lead` and `candidate_snapshot` in a body
     give 422.
   - CSRF on every POST, and GETs never mutate.
   - The injection corpus in any text field.
   - SSE: a session is required, a foreign Origin is refused, the concurrent limit holds.
   - RLS cross-user tests for each new table.
   - Admin hiding: non-admins get 404 from admin routes.
   - Malicious client: weights that don't sum to 1, `min_newcomers` above the team size,
     out-of-range thresholds, a forged seed or snapshot, oversized parameters, all refused or
     ignored.
8. **Screen layouts (§13.9).** Team formation is "the centrepiece" of Demo 2. Follow its layout:
   - settings on the left with presets, the four weight sliders with %, minimum performance and
     newcomers 0/1/2, and "Form team";
   - the result on the right, with the stat row (fitness, price of budget, finish days,
     "✓ Optimal", cost of fairness), TeamCards, "Why this team?", the convergence chart, "Compare
     top 3", "Recalculate" and "Confirm & invite".

   The Reputation page follows its layout too: the six named parameters, competency and
   performance, radar and trend charts, and "Why did this change?".
9. **Unit tests are a supervisor requirement (§16.1).**
   - Backend: every service function, validator, state transition and permission rule gets a
     `unit` test, as well as the API and integration tests.
   - Frontend: every component, hook, form schema and formatter gets a test.
10. **Saved, reproducible runs (FR-TEAM-6).** Runs are stored with their snapshot, parameters and
    seed, and re-running one reproduces it exactly. Decide in the plan how the client sees
    earlier runs.
11. **Each person can explain their modules (§22.10).** `docs/ALGORITHMS.md` gets a plain-English
    section for every algorithm, with a worked example. Raisa will be asked about these in the
    viva.

### Phase 6 — the reputation engine and market simulator

**Build (per §17 Phase 6):**
- `algorithms/reputation.py`: Eq. 1–12 as separate pure functions, plus
  `compute_snapshot(history, settings)`, the newcomer values and the change cap.
- `services/reputation_inputs.py`, which builds the inputs. In this phase they come from
  simulator histories.
- The reputation tables (`reputation_log` append-only, `reputation_skill`).
- `GET /developers/{id}/reputation` and `GET /me/reputation/history`.
- `scripts/simulate_market.py` (§18.3: latent traits, about 30% newcomers, random acyclic
  milestone DAGs, outcomes from traits plus noise, deterministic per seed).
- `make seed-demo STAGE=2` regenerates computed reputations; `reputation_read.py` stays the
  only read path, and the D48 "seeded" marker disappears for computed values.
- The Reputation page (screen 16), built from a reusable **ReputationPanel** component (the
  six parameters with plain labels, C and P), a trend chart and the explanation log; plus the
  reputation summaries on profiles and bid tables.
- `docs/PAPER_ALIGNMENT.md` (equation → function → test) and the reputation section of
  `docs/ALGORITHMS.md` with a worked example.
- **Keep the existing API shape (D58).** `GET /developers/{id}` and the public profile already
  return `reputation = {competency, performance, is_newcomer, seeded}`, and the bid screens show
  it. Fill it with computed values behind the same shape, and `seeded` becomes false.
- **Admin pieces in the navigation.** The admin nav has a "Reputation" entry marked `phase: 6`,
  and §10.2 lists `POST /admin/reputation/recalculate` (step-up, job, `reputation.recalculate_all`
  in §11). In the plan, decide whether Phase 6 builds them or they move to the Phase 12 admin
  console. Record the decision, and update the nav marker if they move.
- **Stage seeds.** In §18.4, STAGE=2 is the full Demo 2 seed (after Phase 12). Phase 6 adds only
  its first part: reputations computed from simulator histories. `make demo-up STAGE=1` and the
  Demo 1 walkthrough (`e2e/demos/demo-1.spec.ts`) must keep working.

**Algorithm quality tests (required, in addition to coverage):**
1. **Each equation by hand.** Eq. 1–12 each get at least two hand-computed fixtures, with the
   arithmetic written in the test's docstring. Include the spec's own:
   - ω for domain counts {2, 1, 1} → 1 − 2/12 = 0.8333;
   - μ for 4 different clients → 1, and for the same client 4 times → 0;
   - an Eq. 2 EWMA sequence;
   - Eq. 5–8 time-slot and cross-project weighting, including α_x < 0.5 (older projects weigh
     more);
   - Eq. 11 with the A2 clip (late work contributes 0);
   - Eq. 12 weights.
2. **One named test per ambiguity:** `test_A1_…` to `test_A13_…`. Each shows the chosen default
   and, where a setting exists, the alternative.
3. **`pcs_replication`:** one test per extension proving it is switched off (change cap,
   evidence weighting, newcomer rule, skill-specific competency and so on).
4. **Properties (Hypothesis):**
   - every output stays in [0, 1];
   - a higher rating never lowers β;
   - more distinct clients never lowers μ;
   - ω doesn't depend on project order;
   - the change cap is never exceeded for X, Xm and β, and never applied to ω, μ and T;
   - newcomer values follow §9.1.3 exactly.
5. **Settings:** κ ≤ 0.5, α_x ≥ 0.5, and weights not summing to 1 are each rejected on save.
6. **Simulator:**
   - the same seed gives byte-identical output;
   - different seeds give different output;
   - the trait distributions and the newcomer share land in their configured ranges;
   - every generated plan is acyclic (run it through `cpm.py`);
   - budgets are consistent with prices.
7. **Does reputation track true ability?** This is E5's question, run as a test. On simulator
   histories, Spearman ρ between computed reputation and the latent traits must be clearly
   positive. Propose the threshold in the plan, then record the measured value in
   `docs/ALGORITHMS.md`. If it fails, investigate before tuning anything.
8. **Golden snapshot:** the stage-2 seed's computed snapshots for named developers are stored as
   a fixture and asserted, so later changes can't drift silently.
9. **Performance:** a 50-project history in under 20 ms (the gate's perf step).
10. **Security and data:** reputation inputs come only from server-side evidence (§14.13 row 6),
    and clients can't write them. `reputation_log` is append-only (trigger). RLS covers each new
    table. The new endpoints are in the authz matrix, have OpenAPI examples, and pass fuzzing.
11. **UI:** screen 16 in all four states and five viewports, light and dark; axe-clean; the trend
    chart has a table alternative; the "Why did this change?" log reads in plain language; the
    newcomer card explains the starting values.

### Phase 7 — team formation

**Build (per §17 Phase 7):**
- **Algorithms:**
  - `algorithms/fitness.py` (Eq. 17–19 with the per-member breakdown);
  - `bpso.py` (Algorithm 2 with the repair operator, locks, archive, early stop, timeout and
    convergence history; seeded `numpy.random.Generator`);
  - `exact_solver.py`;
  - `fairness.py` (cost of fairness; the maximum feasible k fallback);
  - `explain.py` (why this team, risks, comparison, why not selected with the price
    counterfactual).
- **Service and jobs:**
  - `services/formation.py`, which snapshots candidates, settings, parameters and the seed,
    applies quotas and Idempotency-Key, enqueues the job and persists results. The snapshot is
    immutable.
  - The jobs `formation.run` and `formation.explanations`.
  - **The jobs API doesn't exist yet.** Build `GET /jobs/{id}` (requester or admin, 404 for
    anyone else) and `GET /jobs/{id}/events` (SSE), following §10.1 ("long jobs return
    `202 {"job_id"}`") and §10.3. They are shared infrastructure that later phases reuse, so
    keep them generic, not formation-specific.
  - **The quota setting already exists:** `ratelimit.formation_run` (10 per hour) in
    `platform_settings.py`. Apply it with the existing `rate_limit(...)` dependency.
  - SSE progress on `/jobs/{id}/events`. It is the first SSE endpoint in the project, so follow
    §10.3 exactly: cookie auth, Origin check, 20 s heartbeat, a 30-minute cap, at most 3 streams
    per user.
- **How a run starts.** A formation run first runs Algorithm 1 (`filtering.py`, already built)
  with the run's own thresholds P0/C0, advancement choice and relaxation steps. It then passes the
  per-slot shortlist (`K_s = max(shortlist_factor·count_s, shortlist_min)`, D46) to PSO. Reuse
  `filtering.py`; never copy its logic. Report the relaxations in the explanation (§9.7).
- **Numbers.** The PSO and fitness maths may use floats (NumPy). Any score that is stored or
  shown is rounded consistently (3 places, like the reputation columns), and money stays integer
  paisa. Write the rule in the plan and record it as a decision.
- **Scope boundaries.** Don't build Phase 8 here: invitation responses and expiry, lead
  selection, member leaving and team repair. Phase 7's confirm only creates the records Phase 8
  will use. Real work evidence and reviews (Phases 9–11) don't exist yet, so don't build them;
  the simulator stands in for them.
- **Endpoints:** confirm (creates the team, **tentative** availability reservations through
  `availability.py` §9.17, and invitation records; Phase 8 handles the responses) and admin
  verify.
- **SSE through Nginx.** `infra/nginx/proxy-api.conf` buffers API responses and has
  `proxy_read_timeout 30s`, which would break a stream silently. Add a dedicated location for
  `/api/v1/jobs/{id}/events` with `proxy_buffering off`, a read timeout above the 20 s heartbeat,
  and `X-Accel-Buffering: no`. Test the stream **through Nginx** in `tests/edge/test_edge.py`,
  not only in the API tests.
- **Where the job runs.** `formation.run` runs in the RQ worker. Candidate data (reputation,
  skills, evidence) must be read like eligibility is (a SYSTEM session, D50) and frozen into the
  run's candidate snapshot. The snapshot is immutable after that (§14.13 row 7).
- **Notification.** §12 lists "Team formation finished" (in-app, to the client). Use the existing
  `app/services/notifications.py` (used for bid notices, D67).
- **Admin and client navigation.** "Team formation runs" (admin nav, `phase: 7`) and "Teams"
  (client nav `/client/teams`, `phase: 7`) are placeholders, and §10.2 lists
  `GET /admin/formation-runs`. Decide in the Phase 7 plan what Phase 7 builds and what moves to
  Phase 8 or 12. Record it, and leave no menu entry pointing at a page that will never come.
- **Screens:**
  - Screen 24, team formation:
    - PrioritySliders with linked normalization, and presets mapped to the advancement choice;
    - minimum standards with a live pass count, and the FairnessDial;
    - the run, with SSE progress, a live ConvergenceChart and the swarm indicator;
    - result TeamCards with the flip-in animation (a token from `motion.ts`, removed under
      reduced motion) and contribution bars;
    - the stat row, the "Why this team?" panel, TeamComparison, recalculate, and the confirm
      dialog.
  - "Why not selected" on bid detail (screen 12).
- **The homepage rule (D21, backlog P7-H):** `scripts/build_homepage_example.py` produces
  `src/content/homepage-example.json` from a real run, the hero gets its % chip, and the gate
  checks it is fresh.

**Algorithm quality tests (required, in addition to coverage):**
1. **Fitness by hand:** two-member and three-member teams with the breakdown computed in the
   docstring. Infeasible → −∞ (A3). The optional C5·P_i term behaves as specified behind its
   setting (A7). `fitness.use_skill_competency` switches C_i to the per-skill C_{i,s} (§9.1.7)
   and is off by default. Slider weights are normalized so C1 + C2 + C3 + C4 = 1.
2. **Feasibility rules, one test each:** team size, slot counts, distinct developers, budget
   after the fee (A10), skill coverage, `min_newcomers`.
3. **Repair invariants (property tests):** every returned solution is feasible or flagged
   infeasible, locked indices are never removed, and repair is idempotent on an already
   feasible solution.
4. **Determinism:** the same snapshot, parameters and seed give the same team, fitness and
   convergence history, also through the job and the stored run.
5. **Optimality against the exact solver:** on 200 random small instances, PSO is optimal in at
   least 95% with a mean gap of at most 2% (§17). Record the per-instance data; it doubles as
   E1 data. The gate's E1 smoke test uses 20 instances.
6. **Convergence:** gbest never decreases between iterations, early stop triggers after
   `early_stop_iters` without improvement, and a timeout returns the best feasible team with
   `timed_out` set.
7. **Exact solver:** matches brute force on tiny cases; returns the top 3 distinct teams and the
   count; refuses above `exact.max_candidates` (18) or above 2,000,000 combinations; runs 18
   candidates in under 3 s.
8. **Fairness:** the cost of fairness is ≥ 0, exactly 0 when the newcomer minimum isn't binding,
   and 0 when F₀ ≤ 0. If k is impossible, the maximum feasible k is returned with the reason.
   With the fairness dial at 1 on the seeded "Online ordering system", a newcomer is selected.
9. **Explanations are correct, not just present:**
   - the price counterfactual, when applied and re-run, actually selects the bid (property
     test);
   - the "main gap" names the term with the largest weighted gap;
   - rejected and not-shortlisted bids get their filter reasons;
   - the cap of 50 explanations holds;
   - risk chips switch on exactly at their thresholds, tested at the boundaries: Σ price > 95% of
     C, max t > 90% of T^d, mean Xm < 0.5.
10. **Behaviour a person expects (sensitivity tests on fixed instances):**
    - the Budget preset gives a team whose total price is ≤ the Quality preset's;
    - the Quality preset gives mean competency ≥ the Budget preset's;
    - raising the cost weight never raises the total price of the best team on an exact-solvable
      instance;
    - presets map to the right advancement choice;
    - recalculating with a different preset can change the team.
11. **Against a simple baseline:** on simulated jobs, compare with the greedy "top (C + P) within
    budget and slots" baseline (E3's baseline). Report fitness, newcomer share and price, and
    explain any case where greedy wins.
12. **`pcs_replication`:** the repair operator, velocity clamp, newcomer rule and fairness dial
    are off. Infeasible solutions only get the A3 value, and A13 (inertia 1.0) holds.
13. **Security:**
    - formation run quotas, idempotency and timeouts (§14.13 row 7);
    - only the project's client can run or confirm, and only an admin can verify;
    - explanations are visible only to the bidder and admins, enforced in authz **and** RLS,
      with a test that scans every response for other developers' data (like
      `test_role_assessment_api.py`);
    - the SSE endpoint refuses a wrong Origin, other users' jobs, and a fourth stream;
    - every new endpoint is in the authz matrix and passes fuzzing.
14. **Performance:** |S| = 200, N = 10 in under 5 s on this laptop (the gate's step 16).
15. **End to end** (the §17 Phase 7 E2E):
    - the client runs formation with the fairness dial at 1 on the seeded project and sees a
      newcomer selected, the cost of fairness and the verification "Optimal";
    - the client compares teams, recalculates with the Budget preset (the team changes) and
      confirms;
    - a non-selected developer reads a correct explanation.
    Add the screens to `screens.ts` / `stateful-screens.ts`, so axe, the responsive matrix and
    visual baselines cover them.
16. **Manual check, before the gate:** run formation with each preset and fairness level and read
    the explanations aloud as in a viva. If any sentence is wrong or unclear, fix the code or the
    copy.

## Step 8 — Running the gate on this laptop

- **Phase gate:** `make gate PHASE=6`, later `make gate PHASE=7`. It must print
  `PHASE N GATE: PASS`.
- **Run it detached, with sleep blocked.** A suspend froze one run for six hours, and a reboot
  killed another.
  ```bash
  systemd-run --user --unit=devsync-gate-p6 -p OOMScoreAdjust=-500 --working-directory=$PWD --collect \
    systemd-inhibit --what=sleep:idle --why="DevSync gate" \
    bash -c 'python3 backend/scripts/phase_gate.py --phase 6 > runs/gate-p6.log 2>&1'
  ```
  On macOS, use `caffeinate -i nohup python3 backend/scripts/phase_gate.py --phase 6 > runs/gate-p6.log 2>&1 &`.
  On WSL2 the same `systemd-run` command works once systemd is on, but `systemd-inhibit` can't
  stop **Windows** from sleeping. Set Windows "Sleep" to "Never" while it plugs in, and don't
  close the lid.
- **Expect 2–3 hours.** Keep the laptop on power, close browsers and extra editors, and avoid
  updates or restarts. Memory pressure causes browser-test timeouts.
- **When a step fails,** read `runs/gates/failed-*.log`, find the cause, and fix it at the cause.
  If a browser test fails, re-run it alone (`--repeat-each`) before calling it a flake. Then
  re-run the whole gate.
- **The usual causes are listed in the hand-off's gotchas:** new CVEs (rebuild images with
  `--no-cache`, or upgrade one Python package under D51), real input gaps found by fuzzing, and
  timing failures under load.

## Step 9 — Consistency with Phases 0–5 (no compromise)

Phases 6–7 must look and behave as if the same person built the whole product.

**Backend:**
- Same layers (`api → services → repositories → models`; pure `algorithms/`), the same
  `Ctx`-taking services, the same error envelope and codes.
- `StrictRequest` for every body; OpenAPI examples and declared errors on every operation (run
  `make openapi`, which regenerates `schema.d.ts`).
- An authz-matrix entry for every route; RLS (ENABLE + FORCE) on every new table, or an
  `rls_exempt.yml` entry with a reason; definers with a pinned `search_path`.
- Audit entries for state changes, and settings from `platform_settings` (never constants).
- Money in paisa, scores as Decimal at 3 places, times in UTC shown in Asia/Dhaka.
- Migrations `0012+` written like `0004` and `0011`, with a full downgrade.
- After changing the API, run `make openapi` (the contract check compares `docs/api/openapi.json`
  with the code, and the frontend types come from it). After adding tables, run `make erd`
  (`docs/design/erd.svg`).
- Every new module, backend or frontend, needs a test file of its own (`check_module_tests.py`,
  gate step 6).
- Don't break Phases 0–5: every existing test must stay green.

**Frontend:**
- Load `devsync-ui` and `frontend-design` for every screen.
- Use tokens only (no hard-coded colours; status shown as icon + text), and the existing
  components: `Card`, `PageHeader`, `Slider`, `Badge`, `Sheet`, `Dialog`, `ConfirmDialog`,
  `Skeleton`, `EmptyState`, `ErrorState`, `RingProgress`, `toast` and so on.
- Charts follow the custom-SVG pattern of `Gantt.tsx` or use Recharts, with a "View as table"
  toggle and colours from `--chart-1..6`.
  - Before committing to Recharts, prove it is clean under the strict CSP: run `csp.spec.ts` on a
    screen that uses it. It must not inject a `<style>` element.
  - Custom SVG is the proven-safe default here.
- All motion comes from `motion.ts` via `useMotion()`, and reduced motion is respected. The PSO
  swarm indicator is the only looping animation, and only while a job runs.
- Every data view has its four states (loading, empty, error, success).
- Mobile-first: test at 375, 390, 768, 1366 and 1440 px, in light and dark.
- New screens get visual baselines with `make visual-update`. Review the diff and note it in
  `PROGRESS.md`. If the homepage hero changes (D21's % chip), run `make stills`; the gate checks
  the stills manifest.
- Microcopy rules: sentence case, verbs on buttons, curly apostrophes, one sentence of "why" for
  every algorithmic result. Paper terms (C1–C4, Eq. 17) appear only in admin and explanation
  drawers.
- Strict CSP: no inline styles or scripts, no `dangerouslySetInnerHTML`, no libraries that inject
  `<style>`.

**Tests:**
- Never only the happy path: invalid input, boundaries, permission failures and IDOR in every
  feature.
- **Mark every test with the existing pytest markers.** `pyproject.toml` uses
  `--strict-markers`: `unit`, `property`, `integration`, `api`, `security`, `jobs`, `perf`,
  `edge`, `fuzz`. The gate selects by marker: step 10 runs only `security`, step 16 runs `perf`,
  and an unmarked test may never run in the step you expect.
- **Playwright selects tests by tags in their titles:** `@e2e`, `@a11y`, `@visual`, `@perf`,
  `@demo`. A new E2E test without `@e2e` in its title is silently skipped by the gate.
- **E2E setup data goes through the test-only router** (`app/api/v1/test_seed.py`). It exists
  only in the test environment, and `assert_no_test_routes` in `app/main.py` refuses to start if
  it is mounted elsewhere. Add new seeding endpoints there (for example, reputation histories or
  a finished formation run), never to the real API.
- Never remove or weaken a test, threshold or lint rule to pass. The regression guard enforces
  test counts.

**Records, for each phase:**
- the plan in `docs/plans/phase-0N.md`;
- `/security-review`, then `docs/security-reviews/phase-0N.md` (0 unresolved high findings, or
  the gate fails);
- `DECISIONS.md` entries from D83;
- `PROGRESS.md` (session log and current state, every session);
- `docs/ALGORITHMS.md`, `docs/PAPER_ALIGNMENT.md`, `docs/TESTING.md`, `docs/SECURITY.md` and
  `docs/API.md` updated;
- `docs/BACKLOG.md` statuses.

## Rules that apply throughout (from `CLAUDE.md` and spec §0.2)

- **Phase order is strict:**
  - Plan Mode, then an approved plan, then build, then `/security-review` and its document;
  - `make gate PHASE=N` prints PASS;
  - update `PROGRESS.md`, commit `phase-N: <summary>` on the `phase-N` branch, merge to `main`,
    tag `phase-N`, push;
  - then stop and report.
- **Security in every phase:** fail closed, deny by default.
- **Paper formulas exactly as in §9.** Ambiguities use documented, configurable defaults; record
  every deviation.
- **Dependencies:** a new one only if the spec names it (NumPy and Recharts are named) or a
  decision records it. Pin it exactly; it must be at least 14 days old, except a security fix
  under D51.
- **Ask, don't guess.**
- **End every session** by committing work in progress to the phase branch and updating
  `PROGRESS.md`.
- **Git:** never store the GitHub token in git config or files. It is passed per command:
  `git -c http.extraHeader="Authorization: Basic $(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)" push origin refs/heads/<branch> refs/tags/<tag>`.
  Branches and tags share names, so always use `refs/heads/` and `refs/tags/`.
- **Taeen stays available** for questions about Phases 0–5 and the role assessment; Salwa for
  Phases 4–5.
