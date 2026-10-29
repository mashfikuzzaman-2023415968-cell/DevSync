# Testing

| Layer | Command | Where |
|---|---|---|
| Backend unit + API (fast, no Docker) | `cd backend && .venv/bin/pytest -m "unit or api"` | `backend/tests/unit`, `backend/tests/api` |
| Backend all (in the test stack) | `make test-backend` | all backend markers except perf/chaos |
| Edge (Nginx) | gate step 13 | `backend/tests/edge` |
| Frontend unit/component | `make test-frontend` | `frontend/src/**/*.test.tsx`, `frontend/tests` |
| E2E + a11y | `make e2e`, `make a11y` (or gate steps 13–14) | `frontend/e2e` |
| Responsive matrix (5 viewports × light/dark) | part of `@e2e` | `frontend/e2e/responsive.spec.ts`, `layout-checks.ts` |
| Visual baselines (light/dark × 390/768/1440, UI kit) | `make visual`; update with `make visual-update` | `frontend/e2e/visual.spec.ts`, `kit.spec.ts`, `e2e/__screenshots__` |
| Lighthouse + 3D frame rate | gate step 16 (frame rate on the GPU via `infra/playwright-gpu`, D28) | `frontend/scripts/lighthouse.mjs`, `frontend/e2e/perf.spec.ts` |
| Stills | `make stills` (gate checks the manifest hash) | `frontend/scripts/render-stills.mjs` |
| Contract fuzzing + property tests | `make fuzz` (gate step 11; `FUZZ_EXAMPLES=…` to change the budget) | `backend/tests/api/test_schemathesis.py`, `backend/tests/property` |
| Every module has tests | part of `make gate` step 6; `python3 backend/scripts/check_module_tests.py` | `backend/tests/module_tests.json` |
| Full gate | `make gate PHASE=N` | `backend/scripts/phase_gate.py` |

Phase 3 adds: `tests/unit/test_uploads.py` (detection, polyglots, PDF actions, re-encoding,
signing, storage), `tests/unit/test_question_bank_seed.py`, `tests/integration/test_rls_profiles.py`,
`tests/security/test_profiles_files.py`, `tests/security/test_skill_tests.py`,
`tests/jobs/test_profile_jobs.py`; frontend `components/ui/phase3.test.tsx` and
`features/profile/profile.test.tsx`; E2E `e2e/phase3.spec.ts` (with the GPS-tagged fixture
`e2e/files/gps-photo.jpg`). Backend tests that write files use `UPLOAD_DIR=/tmp/uploads` in the
test container.

Role assessment adds (`docs/ROLE_ASSESSMENT.md`): `tests/algorithms/test_role_blueprint.py`,
`test_assessment_selection.py` and `test_assessment_scoring.py` (179 algorithm tests, with the 35
shared vectors in `tests/fixtures/assessment_scoring_vectors.json` that the SQL scoring must match);
`tests/integration/test_role_assessment_db.py` (166: every definer as the web role, RLS on the new
tables, triggers, grants, SQL/Python scoring parity); `tests/security/test_role_assessment_api.py`
(91: lifecycle, one-way answers, window token, deadline and grace, two-leave rule, IDOR, mass
assignment, the 2 KB body limit, admin void/accommodations with step-up, and every JSON response
scanned for answer data); frontend `features/assessment/assessment.test.tsx` (22); E2E
`e2e/role-assessment.spec.ts` (6) and the rewritten Demo 1 walkthrough. The question bank has its
own checks: `make question-bank` (validator, `--check` in the gate) and `make question-checks` (99
execution checks that run each code question's snippet in Python, Node or a throwaway PostgreSQL).

E2E notes: every test starts with fresh rate-limit counters (`e2e/test.ts`, D27) and runs on one
worker; signed-in tests seed users through the test-only router and sign in via the API. Screens
with a fixed address are listed in `e2e/screens.ts`; screens that need state (verification, the
email link, the admin's two-step verification and setup-2fa, a running timed test, a public
profile, a public project) are prepared by `e2e/stateful-screens.ts`, which the axe scan, the
responsive matrix and the visual baselines all iterate.

Contract fuzzing runs three ways (all seeded, so two runs send the same requests): anonymous,
200 examples per operation; signed in as a developer, client, admin and a CSRF-holding guest, 20
examples per operation and role; and a state machine for create project → publish → bid → edit →
withdraw. The signed-in runs exclude only schemathesis's "valid data is accepted" check, because
the server's own rules (password policy, Bangladeshi mobiles, known skill ids, a close time in
the future) are not expressible in JSON Schema; the state machine asserts acceptance where the
input is known to be valid.

Coverage thresholds by phase (backend / frontend): 0–3: 75 / 60; 4–9: 85 / 70; 10–15: 90 / 75.
Security-critical modules and algorithms need ≥ 95% from the phase they appear in.

## Module → tests → coverage (refreshed at each gate)

The tables below are **generated** by `backend/scripts/check_module_tests.py` (gate step 6,
`make gate PHASE=N`, and `python3 backend/scripts/check_module_tests.py --write-doc` on its own).
The same scan fails the gate when a module in `backend/app/` or `frontend/src/` has no test of
its own and no reviewed entry in `backend/tests/module_tests.yml`. Test counts are **static
counts** of test functions (`def test_` in Python, `it(`/`test(` in TypeScript); parametrised and
generated tests expand at run time, so the runners report more.

<!-- module-tests:start -->

<!-- Generated by backend/scripts/check_module_tests.py at every gate; do not edit. -->

### Backend (`backend/app` → `backend/tests`)

Coverage is line + branch coverage of the latest gate run
(`runs/gates/coverage-backend.json`), weighted by statements; the busiest test files
of each package are listed.

| Package | Modules | Tests (files, static count) | Coverage |
|---|---|---|---|
| `app` | 1 | `security/test_role_assessment_api.py` (54), `security/test_rate_limits.py` (24), `unit/test_startup_refusal.py` (18), `api/test_app.py` (16), `api/test_http_hardening.py` (16), `unit/test_config.py` (9), … (3 more) | 99.1 % |
| `app/algorithms` | 8 | `algorithms/test_role_blueprint.py` (37), `algorithms/test_filtering.py` (32), `algorithms/test_cpm.py` (15), `algorithms/test_assessment_scoring.py` (12), `algorithms/test_forecast.py` (11), `algorithms/test_settings_driven.py` (11), … (8 more) | 99.2 % |
| `app/api` | 1 | — | 94.6 % |
| `app/api/v1` | 15 | `security/test_role_assessment_api.py` (54), `security/test_projects.py` (40), `security/test_profiles_files.py` (24), `unit/test_startup_refusal.py` (18), `integration/test_rls_profiles.py` (14), `unit/test_captcha_email_totp.py` (14), … (11 more) | 98.7 % |
| `app/core` | 21 | `integration/test_role_assessment_db.py` (112), `security/test_role_assessment_api.py` (54), `security/test_login_sessions.py` (32), `security/test_profiles_files.py` (24), `security/test_rate_limits.py` (24), `unit/test_security.py` (20), … (33 more) | 97.0 % |
| `app/db` | 4 | `integration/test_role_assessment_db.py` (112), `integration/test_rls.py` (15), `integration/test_rls_profiles.py` (14), `integration/test_foundation_db.py` (11), `integration/test_sessions_ratelimit.py` (11), `jobs/test_bidding_deadline.py` (11), … (12 more) | 98.1 % |
| `app/integrations` | 2 | `unit/test_captcha_email_totp.py` (14), `unit/test_sms.py` (10), `jobs/test_email_jobs.py` (4) | 89.9 % |
| `app/jobs` | 9 | `unit/test_captcha_email_totp.py` (14), `security/test_bid_rules.py` (12), `jobs/test_bidding_deadline.py` (11), `jobs/test_bid_notices.py` (10), `jobs/test_job_runs.py` (7), `jobs/test_profile_jobs.py` (5), … (2 more) | 96.9 % |
| `app/models` | 7 | `integration/test_role_assessment_db.py` (112), `security/test_role_assessment_api.py` (54), `security/test_projects.py` (40), `unit/test_uploads.py` (38), `security/test_bidding_followups.py` (25), `security/test_profiles_files.py` (24), … (19 more) | 100.0 % |
| `app/repositories` | 6 | `security/test_role_assessment_api.py` (54), `security/test_projects.py` (40), `security/test_bidding_followups.py` (25), `security/test_profiles_files.py` (24), `integration/test_rls.py` (15), `integration/test_rls_profiles.py` (14), … (6 more) | 97.9 % |
| `app/schemas` | 11 | `security/test_role_assessment_api.py` (54), `security/test_projects.py` (40), `security/test_profiles_files.py` (24), `integration/test_rls_profiles.py` (14), `unit/test_captcha_email_totp.py` (14), `security/test_marketplace_details.py` (12), … (14 more) | 98.9 % |
| `app/services` | 17 | `security/test_role_assessment_api.py` (54), `security/test_projects.py` (40), `security/test_profiles_files.py` (24), `api/test_app.py` (16), `integration/test_rls_profiles.py` (14), `security/test_marketplace_details.py` (12), … (14 more) | 93.0 % |
| `app/services/auth` | 5 | `security/test_login_sessions.py` (32), `security/test_registration_verification.py` (17), `unit/test_captcha_email_totp.py` (14) | 94.3 % |
| `app/services/testing` | 2 | `security/test_role_assessment_api.py` (54), `unit/test_question_bank_seed.py` (3) | 89.2 % |
| `app/uploads` | 6 | `unit/test_uploads.py` (38), `unit/test_errors.py` (8), `jobs/test_profile_jobs.py` (5), `unit/test_client_errors.py` (5) | 100.0 % |

### Frontend (`frontend/src` → Vitest)

A page's test exercises the components it renders, so a module counts as tested when
a unit test reaches it through its imports. Per-file frontend coverage is not kept
between runs (`frontend/coverage/` is regenerated by the gate); the gate enforces the
phase threshold on statements, branches, functions and lines.

| Area | Modules reached | Tests that import them (static count) |
|---|---|---|
| `frontend/src/api` | 2 | `projects.test.tsx` (57), `plan-features.test.tsx` (22), `assessment.test.tsx` (20), `client.test.ts` (8), `sessionEnded.test.tsx` (8), `shell.test.tsx` (7), … (1 more) |
| `frontend/src/app` | 7 | `guards.test.tsx` (8), `sessionEnded.test.tsx` (8), `shell.test.tsx` (7), `LoginPage.test.tsx` (7), `app.test.ts` (6), `prefetch.test.ts` (5) |
| `frontend/src/components` | 34 | `projects.test.tsx` (57), `profile.test.tsx` (26), `marketplace.test.tsx` (24), `plan-features.test.tsx` (22), `primitives.test.tsx` (20), `assessment.test.tsx` (20), … (18 more) |
| `frontend/src/content` | 1 | `sample.test.ts` (2) |
| `frontend/src/design` | 4 | `projects.test.tsx` (57), `profile.test.tsx` (26), `marketplace.test.tsx` (24), `plan-features.test.tsx` (22), `primitives.test.tsx` (20), `bids.test.tsx` (18), … (14 more) |
| `frontend/src/features/account` | 1 | `profile.test.tsx` (26), `pages.test.tsx` (15), `settings.test.tsx` (9) |
| `frontend/src/features/admin` | 5 | `pages.test.tsx` (15), `guards.test.tsx` (8), `sessionEnded.test.tsx` (8), `LoginPage.test.tsx` (7) |
| `frontend/src/features/assessment` | 9 | `marketplace.test.tsx` (24), `assessment.test.tsx` (20) |
| `frontend/src/features/auth` | 13 | `profile.test.tsx` (26), `marketplace.test.tsx` (24), `assessment.test.tsx` (20), `pages.test.tsx` (15), `settings.test.tsx` (9), `guards.test.tsx` (8), … (8 more) |
| `frontend/src/features/bids` | 7 | `marketplace.test.tsx` (24), `bids.test.tsx` (18), `home.test.tsx` (17), `pages.test.tsx` (15), `guards.test.tsx` (8), `sessionEnded.test.tsx` (8), … (4 more) |
| `frontend/src/features/challenges` | 2 | `profile.test.tsx` (26) |
| `frontend/src/features/home` | 4 | `home.test.tsx` (17), `pages.test.tsx` (15), `guards.test.tsx` (8), `sessionEnded.test.tsx` (8), `shell.test.tsx` (7), `LoginPage.test.tsx` (7), … (1 more) |
| `frontend/src/features/landing` | 22 | `profile.test.tsx` (26), `pages.test.tsx` (15), `landing.test.tsx` (13), `public.test.tsx` (8), `reputation.test.tsx` (5) |
| `frontend/src/features/marketplace` | 4 | `marketplace.test.tsx` (24), `home.test.tsx` (17), `pages.test.tsx` (15), `guards.test.tsx` (8), `sessionEnded.test.tsx` (8), `public.test.tsx` (8), … (3 more) |
| `frontend/src/features/profile` | 10 | `projects.test.tsx` (57), `profile.test.tsx` (26), `marketplace.test.tsx` (24), `plan-features.test.tsx` (22), `home.test.tsx` (17), `pages.test.tsx` (15), … (7 more) |
| `frontend/src/features/projects` | 8 | `projects.test.tsx` (57), `plan-features.test.tsx` (22), `home.test.tsx` (17), `guards.test.tsx` (8), `sessionEnded.test.tsx` (8), `shell.test.tsx` (7), … (2 more) |
| `frontend/src/features/public` | 2 | `public.test.tsx` (8) |
| `frontend/src/lib` | 12 | `projects.test.tsx` (57), `profile.test.tsx` (26), `marketplace.test.tsx` (24), `plan-features.test.tsx` (22), `primitives.test.tsx` (20), `assessment.test.tsx` (20), … (22 more) |

### Modules without tests of their own (reviewed exceptions)

From `backend/tests/module_tests.json`; the gate fails on any module that is neither
covered nor listed here.

| Module | Why |
|---|---|
| `app/api/deps.py` | FastAPI dependencies (session, CSRF-safe acting context, rate-limit keys) run on every API request; tests/security/test_authz_matrix.py drives every route × role through them. |
| `app/api/v1/auth.py` | Route layer of the auth services; covered end to end by tests/security/test_login_sessions.py, test_registration_verification.py and test_admin_totp.py. |
| `app/api/v1/me.py` | Account reads used by tests/security/test_registration_verification.py (status, verification flags) and the profile suites. |
| `app/core/idempotency.py` | Idempotency keys for money endpoints; Phase 10 builds the endpoints that use them and tests replay there (the module is unused until then, 0 % coverage, noted in docs/TESTING.md). |
| `app/core/metrics.py` | Prometheus middleware; tests/api/test_app.py asserts /metrics is served with route templates and tests/edge/test_edge.py that Nginx blocks it from outside. |
| `app/db/base.py` | Declarative base, naming conventions and column mixins — no behaviour of its own; every model and migration test (tests/integration/test_foundation_db.py) loads it. |
| `app/jobs/worker.py` | RQ worker entry point (queues, connection, signal handling); the jobs suite runs tasks with a SimpleWorker, and the stack's worker container is exercised by the gate's E2E run. |
| `app/schemas/common.py` | Shared response and error-envelope helpers; tests/unit/test_errors.py checks the envelope and scripts/check_openapi.py the documented responses they generate. |
| `app/services/auth/account.py` | Sessions and device list; tested through the API in tests/security/test_login_sessions.py. |
| `app/services/auth/common.py` | AuthDeps and shared helpers of the auth services, used by every auth test. |
| `app/services/auth/credentials.py` | Password change, forgot and reset; tested through the API in tests/security/test_login_sessions.py (single-use tokens, expiry, sign-out of every device). |
| `app/services/bidding_terms.py` | Too-few-bids actions (D54); tested through the API in tests/security/test_bidding_followups.py (preview, apply, bounds, If-Match, audit, notifications). |
| `app/services/context.py` | The acting context (who acts, which session, when) passed to every service; built and asserted in every service test. |
| `app/services/notifications.py` | Notification writer; asserted by its effects in tests/security/test_bidding_followups.py and tests/jobs/test_bidding_deadline.py (one notification per closing, per bidder). |
| `app/services/outbox.py` | Email outbox writer; tests/jobs/test_email_jobs.py claims, sends and retries the rows it writes. |
| `app/services/public_stats.py` | Cached homepage counters; tested through the API in tests/api/test_public.py. |
| `frontend/src/app/App.tsx` | Providers and the router outlet; covered by the E2E suite, which loads the real app on every screen of e2e/screens.ts. |
| `frontend/src/app/RoleShell.tsx` | Chooses the shell for a signed-in role; covered by the shell tests and the E2E runs for each role. |
| `frontend/src/app/router.tsx` | Route table; its guards and redirects are unit-tested (src/app/guards.test.tsx) and every route is visited by the E2E screens matrix. |
| `frontend/src/features/admin` | Admin console shell and navigation; Phase 12 builds the console and its tests. Today the bundle is only reachable by a TOTP-verified admin (§14.17), which the E2E a11y run checks. |
| `frontend/src/features/challenges` | Coding challenges; Phase 13 builds the screens and their tests (§17). |
| `frontend/src/features/devtools` | Development-only pages (UI kit, stills) built with VITE_DEV_TOOLS and asserted to be absent from the deployed bundle by the gate (check_no_dev_tools, tests/build/no-inline.test.ts). |
| `frontend/src/features/legal` | Static terms and privacy text; covered by the E2E screens matrix (a11y, responsive, visual). |
| `frontend/src/main.tsx` | Browser entry point (mounts the app); exercised by every Playwright run — there is nothing to unit test that rendering the app does not already cover. |

<!-- module-tests:end -->

### End to end (`frontend/e2e`, Playwright; chromium, firefox, webkit, mobile)

`smoke` (2), `auth` (6), `shell` (7), `home` (11), `csp` (2), `a11y` (2, every screen in
`e2e/screens.ts`), `responsive` (3, viewport matrix), `visual` (4) + `kit` (2) (130 baselines),
`perf` (1, `@gpu`), `phase3` (4), `phase4` (3), `phase5` (6), `role-assessment` (6), `demos/demo-1` (1, the Demo 1
walkthrough). The axe, responsive and visual specs each add one run over the screens that need
state (`e2e/stateful-screens.ts`).

## Latest gate results
See `runs/gates/phase-N.json` and the gate log in `PROGRESS.md`.
