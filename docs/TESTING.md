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
| Full gate | `make gate PHASE=N` | `backend/scripts/phase_gate.py` |

Phase 3 adds: `tests/unit/test_uploads.py` (detection, polyglots, PDF actions, re-encoding,
signing, storage), `tests/unit/test_question_bank_seed.py`, `tests/integration/test_rls_profiles.py`,
`tests/security/test_profiles_files.py`, `tests/security/test_skill_tests.py`,
`tests/jobs/test_profile_jobs.py`; frontend `components/ui/phase3.test.tsx` and
`features/profile/profile.test.tsx`; E2E `e2e/phase3.spec.ts` (with the GPS-tagged fixture
`e2e/files/gps-photo.jpg`). Backend tests that write files use `UPLOAD_DIR=/tmp/uploads` in the
test container.

E2E notes: every test starts with fresh rate-limit counters (`e2e/test.ts`, D27) and runs on one
worker; signed-in tests seed users through the test-only router and sign in via the API.

Coverage thresholds by phase (backend / frontend): 0–3: 75 / 60; 4–9: 85 / 70; 10–15: 90 / 75.
Security-critical modules and algorithms need ≥ 95% from the phase they appear in.

## Module → tests → coverage (refreshed at each gate)

Snapshot of 24 Oct 2026 (end of Phase 5). Test counts are **static counts** of test functions
(`def test_` in Python, `it(`/`test(` in TypeScript) per file; parametrised and generated tests
expand at run time, so the runners report more (last gate: backend 839, frontend 306, E2E 184
per project). Backend coverage is line + branch coverage per module from the latest backend
coverage run (`runs/gates/coverage-backend.json`, 24 Oct, total **95.3 %**, threshold 85 %).
The gate refreshes this section; a gate step that regenerates it automatically is being added
separately — until then, update it by hand after each passing gate.

### Backend (`backend/tests`)

| Module | Test files (static test count) | Coverage |
|---|---|---|
| `app/algorithms` (cpm, forecast, filtering, reputation, availability) | `algorithms/test_cpm.py` (15), `test_forecast.py` (11), `test_filtering.py` (31), `test_reputation_newcomer.py` (5), `test_availability.py` (7); `property/test_filtering_properties.py` (8) | 99.3 % |
| `app/core/security.py`, `captcha.py`, TOTP, email templates | `unit/test_security.py` (16), `unit/test_captcha_email_totp.py` (12) | security 98.6 %, captcha 90.8 % |
| `app/core/sessions.py`, `authz.py`, `auth_middleware.py` | `unit/test_authz_sessions.py` (13), `integration/test_sessions_ratelimit.py` (8), `security/test_authz_matrix.py` (2, every route × role) | sessions 98.6 %, authz 98.2 %, middleware 94.3 % |
| `app/core/csrf.py`, `redirects.py` | `unit/test_csrf_redirects.py` (8) | 100 % / 100 % |
| `app/core/ratelimit.py` | `integration/test_sessions_ratelimit.py` (shared), security suites | 100 % |
| `app/core/config.py`, `logging.py`, `errors.py`, `middleware.py` | `unit/test_config.py` (9), `unit/test_logging.py` (8), `unit/test_errors.py` (8), `api/test_app.py` (16) | 100 %, 100 %, 94.0 %, 92.8 % |
| `app/core/money.py`, `clock.py` | `unit/test_money_and_clock.py` (11) | 98.4 % / 100 % |
| `app/core/audit.py`, foundation migration | `integration/test_foundation_db.py` (11) | 100 % |
| `app/core/idempotency.py` | — (not used until Phase 10) | 0 % |
| `app/db` (RLS context, engines) | `integration/test_rls.py` (15), `test_rls_profiles.py` (14), `test_rls_projects.py` (4), `test_rls_bids.py` (3), `test_health_ready.py` (1) | 98.0 % |
| `app/services/auth` | `security/test_registration_verification.py` (13), `test_login_sessions.py` (29), `test_admin_totp.py` (10) | 94.6 % |
| `app/services/platform_settings.py` | `unit/test_platform_settings.py` (8) | 93.3 % |
| `app/services/profiles.py`, `files.py`; `app/uploads` | `security/test_profiles_files.py` (23), `unit/test_uploads.py` (38) | 96.6 %, 96.9 %; uploads 100 % |
| `app/services/skill_tests.py` | `security/test_skill_tests.py` (9), `unit/test_question_bank_seed.py` (3) | 81.8 % |
| `app/services/projects.py` | `security/test_projects.py` (24) | 97.3 % |
| `app/services/marketplace.py`, `bids.py`, `bidding_terms.py`, `reputation_read.py`, `notifications.py` | `security/test_bids.py` (11), `security/test_bidding_followups.py` (23), `perf/test_bids_view_perf.py` (2) | 91.5 %, 91.2 %, 92.5 %, 94.2 %, 86.4 % |
| `app/services/public_stats.py`, `client_errors.py` | `api/test_public.py` (8), `unit/test_client_errors.py` (5) | 83.9 % / 100 % |
| `app/jobs` | `jobs/test_ping.py` (4), `test_email_jobs.py` (3), `test_profile_jobs.py` (5), `test_bidding_deadline.py` (7) | 94.0 % |
| `app/integrations` (email, sms) | via `unit/test_captcha_email_totp.py`, `jobs/test_email_jobs.py` | 79.3 % |
| `app/api`, `app/schemas`, `app/repositories`, `app/models` | all API/security suites; `api/test_schemathesis.py` (1, whole contract) | 97.3 %, 99.4 %, 98.8 %, 100 % |
| `app/services/testing` (test-only seed router) | used by E2E | 62.0 % |
| Edge (Nginx) | `edge/test_edge.py` (12) | — |
| Gate scripts (`backend/scripts`) | `unit/test_check_forbidden.py` (10), `unit/test_check_scripts.py` (7) | not in app coverage |

### Frontend (`frontend/src`, `frontend/tests`) — threshold 70 % on all four metrics

| Area | Test files (static test count) |
|---|---|
| API client, app shell, guards | `api/client.test.ts` (6), `app/app.test.ts` (6), `app/guards.test.tsx` (7), `components/shell/shell.test.tsx` (5) |
| Design system | `design/contrast.test.ts` (3), `design/design.test.tsx` (8), `components/ui/primitives.test.tsx` (20), `components.test.tsx` (6), `phase3.test.tsx` (11) |
| 3D hero | `components/three/model.test.ts` (5), `three-slim.test.ts` (2) |
| Auth | `features/auth/LoginPage.test.tsx` (6), `RegisterPage.test.tsx` (4), `pages.test.tsx` (12), `schemas.test.ts` (3), `useBotCheck.test.ts` (2); `lib/captcha.test.ts` (2) |
| Landing | `features/landing/landing.test.tsx` (13), `content/sample.test.ts` (2) |
| Profile | `features/profile/profile.test.tsx` (15) |
| Projects, Gantt, CPM | `features/projects/projects.test.tsx` (40) |
| Marketplace, bids | `features/marketplace/marketplace.test.tsx` (7), `features/bids/bids.test.tsx` (9) |
| Lib | `lib/lib.test.ts` (11), `lib/redirects.test.ts` (2) |
| Build | `tests/build/no-inline.test.ts` (5) |

Per-file frontend coverage is not kept between runs (`frontend/coverage/` is regenerated by the
gate); the last gate passed the 70 % threshold on statements, branches, functions and lines.

### End to end (`frontend/e2e`, Playwright; chromium, firefox, webkit, mobile)

`smoke` (2), `auth` (6), `shell` (7), `home` (11), `csp` (2), `a11y` (2, every screen in
`e2e/screens.ts`), `responsive` (3, viewport matrix), `visual` (4) + `kit` (2) (130 baselines),
`perf` (1, `@gpu`), `phase3` (4), `phase4` (3), `phase5` (6), `demos/demo-1` (1, the Demo 1
walkthrough).

## Latest gate results
See `runs/gates/phase-N.json` and the gate log in `PROGRESS.md`.
