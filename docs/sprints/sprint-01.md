# Sprint 1 (Mon 12 Oct – Sun 18 Oct 2026)

**Goal:** Phase 0 gate PASS — a production-shaped empty system with the gate and CI working.
(The spec's timeline also puts the proposal and design documents in this week.)

## Planned items
- P0-1 … P0-9 (see `BACKLOG.md`): repository and working files, config/logging/errors, migration
  0001, Nginx/Compose/DB roles, the phase gate and checkers, frontend scaffold, CI, design skills.
- D0: proposal, use case diagram, ERD, architecture and Gantt chart (§17.0 "pre-demo work").

## Done
Sources: `PROGRESS.md` session log, `git log`. The repository history starts on 17 Oct; work
before that (12–16 Oct) is not recorded in git or `PROGRESS.md`.

| Date | Who | What |
|---|---|---|
| ≤ 16 Oct | team | Proposal `docs/design/DevSync_Proposal_final.pdf` (use case diagram, requirements, Gantt chart) |
| 17 Oct | Taeen | **Phase 0** — foundations, tooling, infrastructure; gate PASS on the fourth run (D15–D18), tag `phase-0` |
| 17 Oct | Taeen | **Phase 1** — accounts, sessions, RLS and security core; gate PASS on the third run (D19–D20), tag `phase-1` |
| 17 Oct | Taeen | **Phase 2** — design system, app shell, homepage with 3D hero; gate PASS (D21–D28), tag `phase-2` |
| 18 Oct | Taeen | **Phase 3** — profiles, portfolio, safe uploads, timed skill tests; gate PASS on the second run (D29–D37), tag `phase-3` |
| 18 Oct | Taeen | Hand-off 01 (Taeen → Salwa) for Phases 4–5 |

The sprint delivered far more than planned: Phases 0–3 instead of Phase 0.

## Review (what was demonstrated)
- `make env certs up migrate` brings up the stack at https://localhost with Mailpit.
- Registration with phone OTP and email link, sign-in, sessions list, sign-out everywhere,
  admin sign-in with TOTP and recovery codes; rate limits and lockout.
- Homepage with the 3D hero, role shells (sidebar, tab bar, command palette), light/dark.
- Developer profile and portfolio with uploads (GPS stripped), certificates, a timed skill test.
- Gate tables per phase in `runs/gates/phase-N.json` (Phase 3: backend 640 / frontend 244 tests).

## Retrospective
- **Went well:** the gate caught real problems early (vulnerable frontend toolchain, CSP
  violations from Zod and Radix, performance on the homepage); every decision is recorded.
- **To improve:** gate runs failed several times on environment issues (Docker snap, Trivy
  DB, Lighthouse, GPU frame-rate check) before code issues; the ERD and architecture diagram
  were not produced in the first week.
- **Actions:** run long gates detached (`systemd-run --user`); write the hand-off before the
  next owner starts; generate the ERD from the models in Phase 4 (`make erd`).
