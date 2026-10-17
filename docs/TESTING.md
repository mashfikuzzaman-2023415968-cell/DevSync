# Testing

| Layer | Command | Where |
|---|---|---|
| Backend unit + API (fast, no Docker) | `cd backend && .venv/bin/pytest -m "unit or api"` | `backend/tests/unit`, `backend/tests/api` |
| Backend all (in the test stack) | `make test-backend` | all backend markers except perf/chaos |
| Edge (Nginx) | gate step 13 | `backend/tests/edge` |
| Frontend unit/component | `make test-frontend` | `frontend/src/**/*.test.tsx`, `frontend/tests` |
| E2E + a11y | `make e2e`, `make a11y` (or gate steps 13–14) | `frontend/e2e` |
| Full gate | `make gate PHASE=N` | `backend/scripts/phase_gate.py` |

Coverage thresholds by phase (backend / frontend): 0–3: 75 / 60; 4–9: 85 / 70; 10–15: 90 / 75.
Security-critical modules and algorithms need ≥ 95% from the phase they appear in.

## Unit-test summary (refreshed at each gate)
_Filled from the latest gate run._

## Latest gate results
See `runs/gates/phase-N.json` and the gate log in `PROGRESS.md`.
