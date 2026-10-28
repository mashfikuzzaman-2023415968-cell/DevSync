# Question bank verification report

Generated 2026-10-28T13:20:08+00:00 by `scripts/question_review.py report` (role assessment spec §13.3).

Every approved question passed (1) an execution check when its answer depends on what code does, and (2) an independent second solve by a fresh reviewer that saw only the question and options. Approved questions are `SELF_VERIFIED`: the team's human review follows after Demo 1 and upgrades them to `HUMAN_APPROVED`.

| Skill | Questions | Approved | By execution | By independent solve only | Failed solve | Failed check | Weak (practice only) | Not yet verified |
|---|---|---|---|---|---|---|---|---|
| DevOps | 31 | 29 | 2 | 27 | 0 | 0 | 1 | 0 |
| FastAPI | 71 | 70 | 29 | 41 | 0 | 0 | 0 | 0 |
| Flutter | 31 | 28 | 0 | 28 | 0 | 0 | 3 | 0 |
| Node.js | 34 | 30 | 7 | 23 | 0 | 0 | 2 | 0 |
| PostgreSQL | 53 | 51 | 25 | 26 | 1 | 0 | 1 | 0 |
| React | 61 | 60 | 21 | 39 | 0 | 0 | 0 | 0 |
| Testing | 58 | 57 | 14 | 43 | 0 | 0 | 0 | 0 |
| UI/UX | 31 | 29 | 0 | 29 | 0 | 0 | 1 | 0 |

## Remaining risks

- No human has reviewed these questions yet; the independent solve catches ambiguity and wrong keys but not every outdated fact. The team review follows after Demo 1.
- Questions marked `check: manual` (no executable answer) rest on the independent solve alone.
- DevOps · Deployment and configuration: approved easy/medium/hard [5, 2, 1] — blueprints use this competency only where the pool can supply it
- Node.js · Error handling: approved easy/medium/hard [2, 3, 1] — blueprints use this competency only where the pool can supply it
- UI/UX · Usability principles: approved easy/medium/hard [6, 2, 0] — blueprints use this competency only where the pool can supply it
