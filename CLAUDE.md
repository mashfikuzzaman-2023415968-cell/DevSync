# DevSync — working rules for Claude Code

Authoritative spec: `DEVSYNC_BUILD_SPEC.md` (read §0–1 first; per phase read §17 + referenced sections).
Paper: `docs/papers/akter2023-pcs.pdf` ([PCS]); §9 of the spec is authoritative for formulas.

## Session start (every person, every time)
1. Read this file, "Current state" in `PROGRESS.md`, the latest `docs/handoffs/` file,
   recent `DECISIONS.md` entries and `docs/plans/phase-NN.md` of the current phase.
2. `git pull`, `make up`, `make migrate`; summarize state + next step before doing anything.

## Session end
Commit WIP to the phase branch, add a session-log entry + update "Current state" in `PROGRESS.md`.

## Phase workflow (spec §0.1)
Plan Mode → plan in `docs/plans/phase-NN.md` → approval → build → `/security-review` →
`docs/security-reviews/phase-NN.md` → `make gate PHASE=N` must print `PHASE N GATE: PASS` →
update PROGRESS.md → commit `phase-N: <summary>`, tag `phase-N` → stop and report.

## Non-negotiables (spec §0.2)
- Phase order is strict; security in every phase (§14.13); fail closed; deny by default.
- Tests cover invalid input, boundaries, permission failures (no happy-path-only tests).
- Paper formulas exactly as §9; ambiguities via documented, configurable defaults (A1–A13).
- `backend/app/algorithms/` is PURE (no DB/web/network/clock); seeded RNG; typed; tested.
- Money: integer paisa; `Decimal` for maths (`app/core/money.py`); never floats.
- Times stored UTC, shown Asia/Dhaka. Never log secrets. Ask, don't guess → `DECISIONS.md`.
- Frontend: load `frontend-design` (+ `devsync-ui` from Phase 2, `threejs-*` for 3D).
- New runtime dependency only if the spec names it or DECISIONS.md records it.
- Never weaken a test, threshold, lint rule or security default to pass the gate.

## Layout
- `backend/` FastAPI app (`app/api → services → repositories → models`; `algorithms` pure),
  `alembic/`, `scripts/` (gate + checkers), `tests/` (unit, integration, api, jobs, edge, …).
- `frontend/` Vite + React + TS strict; tokens in `src/design/`; Playwright in `frontend/e2e/`.
- `infra/` nginx, postgres init, semgrep; compose files at the root.

## Commands
- `make env certs up migrate` — first run (https://localhost, Mailpit http://127.0.0.1:8025)
- `make gate PHASE=N` — the phase gate (`--offline` via `python3 backend/scripts/phase_gate.py`)
- `make test`, `make test-unit`, `make e2e`, `make security`, `make openapi`, `make lock`
- Fast local loop: `cd backend && uv venv --python 3.12 .venv && uv pip sync --python .venv/bin/python requirements.lock requirements-dev.lock`
  then `.venv/bin/pytest -m "unit or api"`; `cd frontend && npm ci && npx vitest run`.
- Changing npm deps: `npx npm@10 install …` (npm 9 has a resolver bug, DECISIONS D15).
