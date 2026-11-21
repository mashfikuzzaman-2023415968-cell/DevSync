# Hand-off 02 — Taeen (and Salwa) → Raisa: Phases 6–7

- **From:** Mashfikuzzaman Taeen (team leader; Phases 0–3, gate fixes for 4–5, role assessment,
  Demo 1 readiness). Salwa Baki built Phases 4–5.
- **To:** Raisa Tabassum (frontend developer), who owns **Phase 6 (reputation engine and market
  simulator)** and **Phase 7 (team formation)**.
- **Date:** 2026-11-21. Template: spec §0.5. The paste-in prompt for Raisa's Claude Code is
  `docs/handoffs/handoff-02-start-prompt.md`.

## 1. Summary

Phases 0–5 are built, gated and tagged (`phase-0` … `phase-5`). Demo 1 (Phases 0–5) was
presented. After `phase-5`, the following were added on `main` and are part of the starting
point:

- **The role assessment** for newcomers (D71–D75; `ROLE_ASSESSMENT_BUILD_SPEC.md`,
  `docs/ROLE_ASSESSMENT.md`). It replaced generic skill tests as newcomer evidence in Algorithm 1.
- **Demo tools:** the developer SMS inbox and quick sign-in tab (`/sandbox/sms`, D76, D78), and
  a fuller stage-1 demo seed (D77).
- **Four fixes found by gate re-runs:** dependency CVEs (D79), a flaky Firefox E2E test (D80), a
  NUL character in request text causing a 500 (D81), and the API coercing `false`/`0` into numbers
  and dates (D82).

**Exact stopping point:** `main` at commit `2a8fa85` plus this hand-off commit. Nothing from
Phase 6 is started.

**Gate status, stated honestly:**

- The last full `PHASE 5 GATE: PASS` is 2026-10-29 (tag `phase-5`).
- On the final code, steps 1–12 passed in one full run (2026-11-20), and steps 14–19 passed in a
  partial run on 2026-11-09.
- Step 13 had 231 passed and 1 failed. The failure is a Firefox-only timing test, see §5.
- **There is no single end-to-end pass on the final commit.** Taeen decided to start Phase 6
  anyway. Every earlier check runs again inside the Phase 6 gate, so this is checked there.

## 2. How to run it from scratch

**Prerequisites:**
- Linux, or Windows with WSL2. Taeen's laptop is Ubuntu with 8 GB RAM.
- Docker Engine 24+ with Compose v2, plus `make`, `git` and Python 3.10+ on the host.
- Node 22 LTS (Phase 6 moves the project from Node 20, see §5) and `uv`
  (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
- About 20 GB of free disk space.

```bash
git clone https://github.com/mashfikuzzaman-2023415968-cell/DevSync.git
cd DevSync
make env          # your own .env with strong random secrets (never committed)
make certs        # dev TLS certificate (mkcert if installed, else openssl, D3)
make up           # dev stack: https://localhost, Mailpit http://127.0.0.1:8025
make migrate      # alembic upgrade head as devsync_migrator
make create-admin # prints the admin's TOTP secret and recovery codes ONCE; keep them private
```

- **If port 80 is taken** (Apache on Taeen's laptop), set `HTTP_PORT=8080` in `.env`.
- **The offline demo stack** (production settings, own database `devsync_demo`) is started with
  `DEMO_PASSWORD='<12+ chars>' make demo-up STAGE=1`. It prints every demo account; with
  `DEMO_PASSWORD`, all accounts share that password. Then run `make demo-preflight`.
- **Phone codes** appear at https://localhost/sandbox/sms. The second tab, Quick sign-in, opens
  any seeded client or developer with one click, never the admin.
- **The test stack**, used by the gate, is project `devsync-test` (`docker-compose.test.yml`).

**Fast local loops** (from `CLAUDE.md`):

```bash
cd backend && uv venv --python 3.12 .venv \
  && uv pip sync --python .venv/bin/python requirements.lock requirements-dev.lock
.venv/bin/pytest -m "unit"           # pure tests, no Docker
cd ../frontend && npm ci && npx vitest run
```

**The phase gate:** `make gate PHASE=N`, which runs `backend/scripts/phase_gate.py`. It takes
about 2–3 hours on an 8 GB laptop. Run it detached (§8).

## 3. What exists (build on it, don't duplicate it)

**Backend:** `api → services → repositories → models`; `app/algorithms/` is pure.

| Area | Files |
|---|---|
| App, middleware, errors | `app/main.py`, `app/core/middleware.py`, `json_body.py`, `errors.py` |
| Auth, sessions, CSRF, authz | `app/services/auth/*`, `app/core/sessions.py`, `csrf.py`, `authz.py` (deny by default; route × role matrix test) |
| RLS context | `app/db/context.py`, `session.py`, `rls_exempt.yml`; helpers in `alembic/versions/0002_identity_rls.py` |
| Request schemas | `app/schemas/common.py`: `StrictRequest` (unknown fields → 422; NUL → 422, D81; bool/number-for-date → 422, D82) |
| Settings | `app/schemas/platform_settings.py`, seeds `alembic/seed/platform_settings_v1..v5.json`; **every Phase 6–7 parameter already exists** here (`rep.*`, `newcomer.*`, `filter.*`, `pso.*`, `exact.*`, `fairness.*`, `fitness.*`, `algorithm.mode`) |
| Money | `app/core/money.py` (integer paisa, Decimal) |
| Profiles, files, practice tests | `app/services/profiles.py`, `files.py`, `skill_tests.py`, `app/uploads/` |
| Projects and CPM | `app/algorithms/cpm.py`, `forecast.py`, `app/services/projects.py` |
| Bids, filtering, availability | `app/algorithms/filtering.py` (Algorithm 1 + newcomer rule), `availability.py`, `app/services/bids.py`, `marketplace.py` |
| Reputation, so far | `app/algorithms/reputation.py` (only `newcomer_snapshot()`), `app/models/reputation.py` (`reputation_snapshots`), `app/services/reputation_read.py` (**the only read path**, D44/D48), `backend/scripts/seed_data/stage1_reputation.json` |
| Role assessment | `app/algorithms/role_blueprint.py`, `assessment_selection.py`, `assessment_scoring.py`, `app/services/role_assessments.py`, migration `0011_role_assessment.py` |
| Jobs | `app/jobs/` (RQ worker, APScheduler that only enqueues) |
| Demo tools | `app/api/v1/sms_sandbox.py`, `app/services/auth/demo_signin.py`, `scripts/seed_demo.py` (stage 1 only so far), `scripts/demo_reset.py` |
| Gate and checkers | `scripts/phase_gate.py` (`phase0_checks` … `phase5_checks`, `role_assessment_checks`, `DEMO_PHASES = {5, 12, 15}`, `CRITICAL_MODULES`), `check_layers.py`, `check_rls.py`, `check_forbidden.py`, `check_openapi.py`, `check_module_tests.py` |

Migrations `0001`–`0011` are in `backend/alembic/versions/`, and the next is `0012`.

**Frontend:**
- Design system: `src/design/` (tokens, `motion.ts`, preferences) and `src/components/ui/*`.
- Shell: `src/components/shell/*`, `src/app/router.tsx`, `navigation.ts`. **The "Reputation"
  (`phase: 6`) and "Teams" (`phase: 7`) entries are coming-soon placeholders to replace.** The
  admin nav has "Reputation" (6) and "Team formation runs" (7).
- Domain composites to reuse: `Gantt.tsx`, `DependencyGraph.tsx`, `CpmTable.tsx`.
- Feature folders: `src/features/*`. The bids folder shows how "why eligible" explanations are
  presented.
- E2E: `frontend/e2e/`. Fixtures are in `fixtures.ts`; screens are listed in `screens.ts` and
  `stateful-screens.ts`, and those lists feed the axe, responsive and visual checks.

**Docs to extend each phase:** `docs/ALGORITHMS.md`, `docs/PAPER_ALIGNMENT.md` (Phase 5 rows
only so far), `docs/SECURITY.md`, `docs/TESTING.md`, `docs/API.md`, `docs/BACKLOG.md`.

## 4. Test and gate status

| | Final code (2026-11-20 run, steps 1–12) |
|---|---|
| Backend | 1,694 passed, coverage 96.5% (minimum 85% for phases 4–9; `app/algorithms/` ≥ 95%) |
| Security suite | 546 passed |
| Contract + fuzzing | 521 passed (anonymous 200 examples per operation, signed-in 20 per operation and role, stateful) |
| Frontend | 506 passed, 80.0% lines (minimum 70%) |
| E2E (demo phase: Chromium, Firefox, WebKit, mobile ×3) | 231 passed, 1 failed (Firefox timing, §5) |
| Steps 14–19 (2026-11-09, earlier code) | axe 6, visual 35 tests / 202 baselines, Lighthouse, phase checks, regression guard: all passed |

**Phases 6 and 7 are not demo phases.** Their E2E step runs Chromium only (×1), which makes
their gates shorter.

## 5. Known issues and limitations

- **Flaky Firefox E2E:** `frontend/e2e/role-assessment.spec.ts:181` ("opening the attempt in
  another window stops this one").
  - The second tab's `page.goto` times out in some full runs, even with `domcontentloaded`. It
    passes 10 of 10 when run alone.
  - Suspected cause: Nginx request limiting, or connection queuing when one IP opens a second
    tab under load. This is not proven.
  - It doesn't run in the Phase 6–7 gates (Chromium only), but **must be fixed before the Demo 2
    gate (Phase 12)**.
  - Fix it at the cause, never with retries or by loosening the test.
- **Node 20 is end of life** (`PROGRESS.md` known issues, D15). Backlog item P6-0 is to move the
  laptops and the Nginx build stage to Node 22 LTS at the start of Phase 6. Re-run the frontend
  build and tests afterwards.
- **NumPy and Recharts are not installed yet.** The spec names both (§3: NumPy for algorithms,
  Recharts for charts), so they may be added. Pin exact versions at least 14 days old and record
  them in `DECISIONS.md`.
- **SSE doesn't exist yet.** Phase 7's formation progress is the first Server-Sent Events
  endpoint (§10.3: cookie auth, Origin check, 20 s heartbeat, 30 min close, max 3 streams per
  user). Build it carefully: it sets the pattern for notifications later.
- **The demo port is reachable from the network** (D76, D78): the demo stack's port is open on
  all interfaces, which exposes the inbox and quick sign-in on fake data. Binding it to
  127.0.0.1 is still open.
- **Open human checks:** the accuracy review of the 128 practice questions (D34/D74), and the
  tester's manual check of `docs/security-reviews/role-assessment.md`.
- **Self-signed certificate:** install mkcert for a trusted one.

## 6. Open decisions and questions

- The next decision number is **D83**.
- **Demo 2 is Monday 7 December 2026** and covers Phases 6–12 (spec §17.0). Phases 8–12 are not
  assigned yet. **Confirm the date and the owners with Taeen.**
- §17.0 lists what may move if Demo 2 is at risk: team comparison, client analytics and file
  previews. The research core (reputation, BPSO, exact verification, fairness dial) never moves.
- The supervisor questions in spec §23, including the A1–A13 resolutions, are still unanswered.
  The defaults stand.

## 7. Things Phases 6–7 depend on (don't change without care)

- **`services/reputation_read.py` stays the only read path for reputation.**
  - Phase 6 replaces the fixed stage-1 snapshots with computed ones behind it.
  - Algorithm 1 (`filtering.py`) and the bid screens read through it.
  - The "seeded" marker (D48) must disappear once values are computed.
- **The newcomer rule now uses role-assessment evidence** (D71–D72): a valid pass for the slot.
  - ω⁰ for newcomers counts domains with a passing skill evidence (a valid role-assessment pass
    or a passing practice result; see `_evidence_domains`).
  - Keep these semantics in fitness and in the fairness dial ("newcomer" means fewer than
    `newcomer.threshold` completed projects).
- **`algorithm.mode`:** `pcs_replication` must switch off every DevSync extension (§9.0). Phase 5
  already respects it in filtering. Phases 6–7 must do the same, with a named test per extension.
- **Pure algorithms:** no DB, web, network or clock; seeded `numpy.random.Generator`; Decimal or
  float use documented. `check_layers.py` enforces it, and the coverage floor for
  `app/algorithms/` is 95%.
- **Sealed bids:** formation explanations are visible only to the bidder and admins (§14.13 row
  7). Add them to the authz matrix and RLS like bids.
- **Money in paisa**, including counterfactual prices (rounded down to ৳100 = 10,000 paisa,
  §9.8).
- **The homepage rule (D21):** Phase 7 must add `scripts/build_homepage_example.py`,
  `src/content/homepage-example.json`, the % chip and the gate freshness check (backlog P7-H).
  Homepage numbers must come from a real PSO run.

## 8. Gotchas (hard-won)

- **Run the gate detached and block sleep.** A suspend froze one run for 6 hours; a reboot
  killed another.
  ```bash
  systemd-run --user --unit=devsync-gate-p6 -p OOMScoreAdjust=-500 --working-directory=$PWD --collect \
    systemd-inhibit --what=sleep:idle --why="DevSync gate" \
    bash -c 'python3 backend/scripts/phase_gate.py --phase 6 > runs/gate-p6.log 2>&1'
  ```
  On macOS use `caffeinate -i` with `nohup`. Avoid updates and reboots while it runs.
- **8 GB RAM is tight.** Close browsers and extra editors during the gate. Memory pressure
  causes E2E timeouts.
- **The container scanner (step 7) fails on newly published CVEs** in stale Debian layers.
  Rebuild without the cache:
  `docker compose -p devsync-test -f docker-compose.yml -f docker-compose.test.yml --profile tools build --no-cache api tests nginx`.
  If the Nginx stage's `npm ci` hits a transient exit 146, retry.
- **pip-audit finds new Python CVEs:** upgrade only that package,
  `uv pip compile requirements.in --python-version 3.12 --generate-hashes -o requirements.lock --upgrade-package NAME==FIXED`,
  and record it (D51 allows a security fix to be newer than 14 days; see D79).
- **Schemathesis finds real input gaps** (D81, D82). Fix them in the API, never by excluding
  checks. First run the tests guarding nearby behaviour (see D81: two first attempts broke other
  tests).
- **The test stack bakes code into images.** After backend changes run `... build api tests`,
  then `up -d --force-recreate --wait api`; after frontend changes rebuild `nginx` before E2E.
- **Migrations:** autogenerate inside the backend image (command in handoff-01 §8), then add RLS
  (ENABLE + FORCE), policies, definers with a pinned `search_path`, and grants by hand. Verify
  upgrade → downgrade → upgrade and `alembic check`.
- **SQLAlchemy:** assign enum members, not strings; re-read rows changed by definers with
  `populate_existing`.
- **Vitest and MSW:** within one `server.use(a, b)` the earlier handler wins. `tsc -b` (used by
  the production build) also type-checks test files: an `unknown` MSW body broke a build once.
- **Navigation in tests:** use `pageLoad.to()` from `src/lib/redirects.ts` for full page loads,
  so tests can spy on it. Stubbing `window.location` breaks the router.
- **E2E rate limits:** every request comes from one IP. Tests reset limits through
  `e2e/test.ts`; long flows call `/api/v1/__test__/ratelimits/reset` (D27).
- **Git:** branches and tags share names (`phase-5`). Push with `refs/heads/...` and
  `refs/tags/...`. Push tokens are passed per command and never stored.
- **`.env` can't be `source`d.** Read single values with `grep '^NAME=' .env | cut -d= -f2-`.

## 9. Read first

1. `CLAUDE.md`, then the "Current state" in `PROGRESS.md`, then this document.
2. `DEVSYNC_BUILD_SPEC.md`:
   - §0–§1 in full;
   - §17 Phase 6 and Phase 7 word for word;
   - all of §9 (especially §9.0, §9.1, §9.3–§9.8 and §9.14 for the trust formula);
   - §6.2, §7.4, §7.7, §10.2–§10.3, §11, §13.5 screens 12, 16 and 24, §14.13 rows 6–7,
     §16.4–§16.5, §18.3–§18.4 and §19.
3. `DECISIONS.md`, all of it (D1–D82).
4. `docs/papers/akter2023-pcs.pdf`, Sections 4.1–4.5 (reputation, Algorithm 1, fitness, BPSO).
   §9 of the spec is authoritative.
5. `docs/plans/phase-05.md` and `docs/security-reviews/phase-05.md`, plus `docs/ALGORITHMS.md`
   and `docs/PAPER_ALIGNMENT.md`.

## 10. Secrets and setup

- **Generate your own secrets** with `make env`, and your own admin with `make create-admin`.
  Never commit `.env`, certificates or `runs/` output.
- **The GitHub push token is passed privately**, per command:
  `git -c http.extraHeader="Authorization: Basic $(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)" push origin refs/heads/<branch> refs/tags/<tag>`.
  Never store it, and revoke it after use.
- **No secrets were handed over in this document.**
- **Taeen stays available** for questions about Phases 0–5 and the role assessment.
