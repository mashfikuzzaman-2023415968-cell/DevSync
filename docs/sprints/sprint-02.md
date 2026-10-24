# Sprint 2 (Mon 19 Oct – Sun 25 Oct 2026)

**Goal:** Phases 4 and 5 gates PASS — projects with the CPM planner, the marketplace with
sealed bidding and Algorithm 1 filtering — so the Demo 1 walkthrough runs end to end.

## Planned items
- P4-1 … P4-5: CPM/forecast algorithms, migration 0005, project API, wizard and plan page, ERD.
- P5-1 … P5-6: migrations 0006/0007, Algorithm 1 filtering, marketplace and recommendations,
  sealed bids, too-few-bids handling, Demo-1 tooling.
- Owner: Salwa (Phases 4–5, from hand-off 01); review and gate support: Taeen.

## Done
Sources: `PROGRESS.md` session log and gate log, `git log`.

| Date | Who | What |
|---|---|---|
| 19 Oct | Salwa | Phase 4 backend (pure CPM + forecast, migration 0005, 14 routes, authz, ERD generator) and frontend (wizard, Gantt, dependency graph, CPM table, My Projects); D38–D42; security review phase-04 |
| 19–20 Oct | Taeen | Phase 4 review: wrote the missing E2E, which exposed broken wizard saves, impossible publishing and a plan graph without edges; fixed (D43); gate PASS |
| 20 Oct | Salwa | Merged and tagged `phase-4`; Phase 5 plan approved and built end to end (migration 0006, `filtering.py`, marketplace + bids services, 12 routes, deadline job, stage-1 seed, screens); D44–D50; security review phase-05 |
| 21 Oct | Taeen | Phase 5 review and gate (9 runs): vulnerable Pillow/certifi (D51), route shadowing and query bounds (D52), first cross-browser E2E fixes (D53); gate PASS |
| 22 Oct | Taeen | Merged and tagged `phase-5`; Demo 1 readiness check exposed demo accounts that could not sign in; built the external-review follow-ups (D54: bidding closes by time, explained verdicts, too-few-bids actions, search, recommendations) |
| 23 Oct | Taeen | Follow-ups gate PASS and `make demo-check DEMO=1` passed (gate + walkthrough 12/12); `phase-5` re-tagged; Gantt polish (date axis, arrows, legend, zoom, today line); gate PASS |
| 24 Oct | Taeen (Claude Code) | Demo 1 documents: architecture, diagrams, UI guide, STRIDE table, backlog, sprints, testing table |

Last gate (23 Oct 12:15 UTC): backend 839 tests (95.3 % coverage), security suite 278,
frontend 306, E2E 184 × 3 on chromium/firefox/webkit/mobile, 130 visual baselines,
Lighthouse desktop 100 / mobile 94.

## Review (what was demonstrated)
`make demo-check DEMO=1` — the scripted Demo 1 walkthrough (`frontend/e2e/demos/demo-1.spec.ts`):
landing page → client registers and verifies → admin signs in with TOTP → client creates a
6-milestone project; the CPM timeline shows the critical path and slack; a circular dependency
is rejected → newcomer completes a profile and passes a timed skill test → developers search
and place sealed bids; one bid shows why it would be filtered out → a second developer cannot
see the first bid → the client sees all bids with eligibility reasons and the too-few-bids
banner.

## Retrospective
- **Went well:** the hand-off worked (Salwa ran Phases 4–5 from the document); review by the
  previous owner plus real-stack E2E found defects unit tests missed; the security reviews and
  DECISIONS entries kept every change explainable.
- **To improve:** Phase 4 was first delivered without the E2E that would have shown broken
  saves; many gate runs were lost to the laptop (memory pressure with Chrome open, a battery
  that would not charge, swap exhaustion during Vitest with coverage); cross-browser testing
  started only at the first demo phase.
- **Actions:** write the phase E2E before calling a phase done; cap Vitest workers (done) and
  close Chrome during gates; keep `make demo-check` as the last step before any demo merge.
