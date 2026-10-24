# Sprint 3 (Mon 26 Oct – Sun 1 Nov 2026) — current / planned

**Goal:** Demo 1 ready (Mon 2 Nov): Phases 0–5 merged, pushed and rehearsed on the demo laptop,
with the readiness window (30 Oct – 1 Nov, spec §17.0) used for polish, not new features.

## Planned items
Owners are proposals by role (§17.0 timeline: readiness check by QA) for the team to confirm at
sprint planning.

| Item | Proposed owner | Notes |
|---|---|---|
| Merge `gantt-polish` (and pending documentation branches) into `main`, push | Taeen | Full gate + cross-browser repeats before the push |
| D1-1 Rehearsal on the demo laptop: mkcert certificate (D3), `make demo-up STAGE=1`, `make demo-preflight`, `make demo-reset` between runs | team | `HTTP_PORT=8080` where Apache holds port 80 |
| `make demo-check DEMO=1` on the demo laptop; keep `runs/demos/demo-1.md` and the video as the fallback | Sara | |
| Polish pass against §13.8 on the demo-path screens (states, microcopy, dark mode, phones) | Raisa | No new features |
| D1-2 Human check of security reviews 00–05 | Sara | Open since Phase 0 |
| P3-5 Review of the 128 drafted skill-test questions (D34) | team | Before the newcomer test is shown live |
| Sanity-check D39 (simulated payment-method verification) | Salwa | |
| D1-3 Tag `v0.1.0` after the demo | Taeen | §17.1 |
| Prepare Phase 6: move to Node 22 LTS (D15), plan in Plan Mode | Taeen | Phase 6 starts 2 Nov |

## Done
_(fill in during the sprint from `PROGRESS.md`)_

## Review
_(at sprint end: the Demo 1 presentation and the supervisor's feedback)_

## Retrospective
- Went well:
- To improve:
- Actions:
