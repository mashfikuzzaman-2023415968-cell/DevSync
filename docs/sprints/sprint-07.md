# Sprint 7 (Mon 23 – Sun 29 Nov 2026)

Sprints 4–6 have no notes; they resume here (PROGRESS.md records the gap).

**Goal:** finish Phase 8, then build the Phase 9 workspace with the Demo 2 path first.

## Items

| Item | Owner | Result |
|---|---|---|
| Phase 8 gate on the native Linux laptop, merge, tag `phase-8` | Taeen | PASS (`f7fedc1`) |
| Phase 9 set-up on the WSL laptop, the study, the plan (D141–D172) | Sara | Approved |
| Items 1–7 (D159): migration 0016 and RLS; tasks and the Kanban board; check-ins; comments; evidence events; monitoring; the Inventory seed | Sara | Done |
| Items 8–12: files; discussion; live notifications and preferences; Evidence tab, My projects, dashboards; DAST | Sara | Done (D175–D177) |
| End-to-end test, docs, security review, push for the gate | Sara | In progress |

## Review

The Demo 2 path works end to end: a lead plans tasks, members move them and check in, and the
client watches progress and risks. On day 12 the seeded Inventory project shows exactly the
documented forecast and four risks. ZAP's first signed-in scan found no High, Medium or Low
alerts.

## Retrospective

- **Went well:** one decision rule for open points, recorded as they came up (D173–D177);
  committing and reporting after every item.
- **To improve:** this laptop's limits cost hours. BuildKit crashes when two images build
  together, the 3.7 GB ZAP pull took 55 minutes, and Vitest timed out under parallel load.
- **Actions:** build images one at a time; run heavy suites alone; pull the ZAP image before
  the gate.
