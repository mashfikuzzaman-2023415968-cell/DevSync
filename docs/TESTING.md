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

## Unit-test summary (refreshed at each gate)
_Filled from the latest gate run._

## Latest gate results
See `runs/gates/phase-N.json` and the gate log in `PROGRESS.md`.
