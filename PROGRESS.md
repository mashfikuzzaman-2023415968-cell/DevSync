# DevSync progress

## Current state
- **Current owner:** Salwa Baki (backend developer), Phases 4–5, from 2026-10-18 (hand-off from Mashfikuzzaman Taeen: `docs/handoffs/handoff-01-taeen-to-salwa.md`); Phase 5 gate finished by Taeen.
- **Current phase:** 5 done (merged into `main`, tagged `phase-5` on 2026-10-22 by Taeen; push to GitHub pending a token). Next: Phase 5 follow-ups before Demo 1, then Phase 6.
- **Last gate result:** `PHASE 5 GATE: PASS` (2026-10-21 20:00 UTC, Taeen's laptop, branch `phase-5`): backend 785 tests (95.4% coverage), security suite 246, frontend 283, E2E 177 × 3 on chromium/firefox/webkit/mobile, visual 112 baselines, Lighthouse desktop 97 / mobile 94.
- **In progress:** Phase 5 follow-ups (D54) on branch `phase-5-followups` (worktree `../DevSync-p5f`): bidding closes by time, bids reference only the bidder's portfolio, the client Bids screen explains every verdict (Algorithm 1 trace, newcomer rule, relaxation, cheapest team, filters, phone cards), the five too-few-bids actions with previews, replication-mode relaxation as in the paper, search pagination for every sort and skill-name search, recommendations per §9.16, reserved-domain sign-in for the demo accounts, the bundled breached-password list committed (it was gitignored), hero poster on software WebGL. Being tested end to end before merging into `main`.
- **Very next step:** full `make gate PHASE=5` on the branch, `/security-review`, `make demo-check DEMO=1`; then merge into `main`, re-tag, push (token from Taeen). Demo 1 is Mon 2 Nov 2026 (Phases 0–5).
- **Open human tasks:** review the 128 drafted test questions (D34); tester's human check of the Phase 3, 4 and 5 security reviews; sanity-check D39 (simulated payment-method verification).

## Phase table
| Phase | Owner | Status | Gate | Date | Tag |
|---|---|---|---|---|---|
| 0 Foundations | Taeen | done | PASS | 2026-10-17 | phase-0 |
| 1 Accounts & security core | Taeen | done | PASS | 2026-10-17 | phase-1 |
| 2 Design system & landing | Taeen | done | PASS | 2026-10-17 | phase-2 |
| 3 Profiles & skill tests | Taeen | done | PASS | 2026-10-18 | phase-3 |
| 4 Projects & CPM | Salwa (review fixes: Taeen) | done | PASS | 2026-10-20 | phase-4 |
| 5 Marketplace & filtering | Salwa (gate fixes: Taeen) | done | PASS | 2026-10-21 | phase-5 |
| 6–15 | — | not started | — | — | — |

## Gate log (newest first, appended by `make gate`)
| Finished (UTC) | Phase | Result | Tests |
|---|---|---|---|
<!-- gate-log -->
| 2026-10-22T12:36:38+00:00 | phase 5 | PASS | backend 839 / frontend 291 tests |
| 2026-10-22T10:47:58+00:00 | phase 5 | FAIL (step 13) | backend 839 / frontend 291 tests |
| 2026-10-22T09:26:09+00:00 | phase 5 | FAIL (step 13) | backend 839 / frontend 291 tests |
| 2026-10-22T05:58:19+00:00 | phase 5 | FAIL (step 13) | backend 785 / frontend 283 tests |
| 2026-10-21T20:00:03+00:00 | phase 5 | PASS | backend 785 / frontend 283 tests |
| 2026-10-21T17:12:45+00:00 | phase 5 | FAIL (step 13) | backend 778 / frontend 283 tests |
| 2026-10-21T14:14:09+00:00 | phase 5 | FAIL (step 13) | backend 775 / frontend 283 tests |
| 2026-10-21T11:35:34+00:00 | phase 5 | FAIL (step 3) | backend 775 / frontend 278 tests |
| 2026-10-19T20:26:29+00:00 | phase 4 | PASS | backend 716 / frontend 269 tests |
| 2026-10-19T20:05:41+00:00 | phase 4 | FAIL (step 3) | backend 716 / frontend 269 tests |
| 2026-10-19T19:17:13+00:00 | phase 4 | PASS | backend 716 / frontend 267 tests |
| 2026-10-19T16:34:19+00:00 | phase 4 | FAIL (step 13) | backend 716 / frontend 267 tests |
| 2026-10-19T15:53:38+00:00 | phase 4 | FAIL (step 13) | backend 716 / frontend 267 tests |
| 2026-10-19T15:20:24+00:00 | phase 4 | FAIL (step 13) | backend 716 / frontend 267 tests |
| 2026-10-19T13:15:27+00:00 | phase 4 | FAIL (step 5) | backend - / frontend - tests |
| 2026-10-19T13:12:14+00:00 | phase 4 | FAIL (step 4) | backend - / frontend - tests |
| 2026-10-19T13:08:46+00:00 | phase 4 | FAIL (step 3) | backend - / frontend - tests |
| 2026-10-19T13:06:36+00:00 | phase 4 | FAIL (step 3) | backend - / frontend - tests |
| 2026-10-19T06:08:02+00:00 | phase 3 | FAIL (step 13) | backend 674 / frontend 244 tests |
| 2026-10-19T05:27:47+00:00 | phase 3 | FAIL (step 12) | backend 674 / frontend - tests |
| 2026-10-19T05:09:26+00:00 | phase 3 | FAIL (step 12) | backend 674 / frontend - tests |
| 2026-10-19T04:44:45+00:00 | phase 3 | FAIL (step 6) | backend - / frontend - tests |
| 2026-10-18T20:25:28+00:00 | phase 3 | FAIL (step 7) | backend - / frontend - tests |
| 2026-10-18T06:26:08+00:00 | phase 3 | PASS | backend 640 / frontend 244 tests |
| 2026-10-18T06:07:55+00:00 | phase 3 | FAIL (step 3) | backend 640 / frontend 244 tests |
| 2026-10-17T16:43:18+00:00 | phase 2 | PASS | backend 445 / frontend 218 tests |
| 2026-10-17T16:20:47+00:00 | phase 2 | FAIL (step 7) | backend 445 / frontend 0 tests |
| 2026-10-17T14:03:25+00:00 | phase 2 | FAIL (step 9) | backend - / frontend - tests |
| 2026-10-17T12:42:39+00:00 | phase 2 | FAIL (step 5) | backend - / frontend 217 tests |
| 2026-10-17T07:17:01+00:00 | phase 1 | PASS | backend 417 / frontend 132 tests |
| 2026-10-17T06:19:59+00:00 | phase 1 | FAIL (step 13) | backend 417 / frontend 130 tests |
| 2026-10-17T06:10:47+00:00 | phase 1 | FAIL (step 5) | backend - / frontend 130 tests |
| 2026-10-17T04:48:38+00:00 | phase 0 | PASS | backend 182 / frontend 52 tests |
| 2026-10-17T04:45:33+00:00 | phase 0 | FAIL (step 9) | backend - / frontend 52 tests |
| 2026-10-17T04:40:20+00:00 | phase 0 | FAIL (step 7) | backend - / frontend 52 tests |
| 2026-10-17T04:28:22+00:00 | phase 0 | FAIL (step 3) | backend - / frontend 52 tests |

## Known issues
- This laptop runs Apache on port 80: for `make up`, set `HTTP_PORT=8080` in `.env` or stop Apache.
- `make certs` produced a self-signed certificate; install mkcert before Demo 1 (D3).
- Node 20 is end-of-life; move the team to Node 22 LTS before Demo 1 (D15).
- Tester's human check of `docs/security-reviews/phase-00.md` to `phase-03.md` is pending (Sara).
- The 128 skill-test questions need a human accuracy review (D34).
- The gate's frame-rate step needs a GPU (`/dev/dri`); run the gate on a laptop (D28). Long gate runs are best started with `systemd-run --user` so closing a terminal or chat doesn't kill them.
- The 2021 STI paper is cited without a link (no DOI found); add the IEEE Xplore URL when known.
- Existing dev databases: run `make migrate` (migration 0002); create an admin with `make create-admin`.
- Phase 5 known limitations (D54): TOO_SLOW compares with the whole-project deadline, not the slot's milestones (the paper's simplification); availability must be re-checked when invitations are accepted (Phase 8); bid prices stay visible to the client during bidding (spec), sealed from other developers.

## Session log (newest first)
### 2026-10-22 — Taeen (with Claude Code), Phase 5 merged; follow-ups
- Merged `phase-5` into `main` (fast-forward) and tagged `phase-5`; `make demo-check DEMO=1` exposed that the seeded demo accounts (`@devsync.local`) could not sign in and that the walkthrough expected screens it never reached.
- Built every item of the external Phase 5 review on `phase-5-followups` (D54, security review findings 6–8) with property, API, job, perf, unit and cross-browser E2E tests and visual baselines for the bidding screens.
- Found and fixed on the way: the bundled breached-password list was never committed (`data/` ignore rule); the client view read ORM rows after its SYSTEM session closed (500); the shared dialog close button shrank on phones; `demo-check` left the test stack unseeded when the gate stopped early.

### 2026-10-21 — Taeen (with Claude Code), Phase 5 review and gate
- Reviewed Salwa's Phase 5 and ran the gate until `PHASE 5 GATE: PASS` (run 9 of the day; runs 4–6 were cut short by a battery that would not charge).
- Real defects fixed: vulnerable Pillow/certifi (D51); `/projects/{id}` shadowing search routes, query bounds, float-free ordering (D52); WebKit could send an empty CSRF header after `GET /auth/csrf` (token now echoed in a header); sign-up's automatic sign-in now solves the CAPTCHA when asked; NUL/control characters in search → 500 (now cleaned, skill filters capped at 20); sign-out does a full page load; hero headline accessible name; 44 px touch targets (D53, security review findings 3–5).
- E2E robustness: viewport-aware helpers, smooth scrolling off in tests, homepage link tests on reduced motion (software WebGL in the container), gitleaks skips Playwright output.
- Not merged or tagged; follow-ups recorded under Known issues.

### 2026-10-20 — Salwa (with Claude Code), Phase 5 build
- **Done:** approved `docs/plans/phase-05.md`; built Phase 5 end to end on `phase-5`. Backend —
  migration 0006 (bids/reservations/reputation_snapshots + project search, sealed-bid RLS, SYSTEM
  eligibility policies D50); pure `filtering.py` (Algorithm 1 + newcomer rule + relaxation +
  shortlist), `reputation.py` (newcomer_snapshot), `availability.py`; `reputation_read`; marketplace
  + bids services and 12 routes; authz matrix; bidding-deadline job; stage-1 seed + `phase5_checks`.
  Frontend — Find Projects, bid sheet with live eligibility, My Bids, client Bids + too-few banner.
- **Tests:** 35 algorithm (99%), ~60 backend in the stack (bids API, RLS bids/projects, authz
  matrix, jobs, seed self-assertion), 278 frontend (≥70% all metrics). Decisions D44–D50; security
  review phase-05 (0 unresolved high).
- **Next:** `phase5.spec.ts` + Demo-1 tooling + visual baselines, then the full gate.

### 2026-10-20 — Salwa (with Claude Code), Phase 4 merge
- **Done:** reviewed Taeen's Phase 4 fixes (DECISIONS D43) and agreed with all of them — several
  fixed real defects in the original frontend (the `"preview"` placeholder id, GET hooks on
  endpoints that don't exist, missing payment-verify UI, plan-graph edges). Re-verified on this
  laptop: `tsc -b`, eslint, prettier, vitest (269), backend `pytest -m "unit or api"` (347;
  stack-only tests skipped here, green on Taeen's gate), DB at `0005`. Skipped the full-stack
  `phase4.spec.ts` locally (2.6 GB free → D28 flake risk; already PASS on Taeen's gate).
- **Merged** `phase-4` into `main` (ff-only) and **tagged `phase-4`** at `5b4edc5`.
- **Next:** Phase 5 in Plan Mode.

### 2026-10-20 — Taeen (with Claude Code), Phase 4 review
- **Done:** pulled `phase-4`; ran the gate (PASS as delivered on this laptop); reviewed against
  the spec and wrote the missing Phase 4 E2E, which exposed broken wizard saves, impossible
  publishing, no loop demo, a plan graph without edges, and missing spec items — all fixed (D43),
  with unit/API/E2E tests and visual baselines for the planning screens. Gate PASS.
- **Next:** Salwa merges and tags `phase-4`, then Phase 5.

### 2026-10-19 — Salwa (with Claude Code), Phase 4
- **Done (backend, earlier in the day):** pure CPM + forecast algorithms (`app/algorithms/`,
  §18.2 golden verified, 300-milestone CPM < 50 ms); migration `0005` (7 tables, FORCE RLS,
  `is_project_client`/`project_visible` definers, baseline-immutability + publish-guard triggers);
  project schemas/repository/service (draft CRUD, whole-set slot/milestone/dependency replace,
  CPM-cycle → 422, publish §8 guards, extend-bidding cap, cancel, payment-verify D39); 14 routes
  with OpenAPI examples; authz policies + matrix rows; 34 backend + 35 algorithm tests; ERD
  generator (`make erd`) and `phase4_checks`. Decisions D38–D42.
- **Done (frontend, this session):** regenerated `schema.d.ts`; `features/projects/api.ts` (15
  TanStack Query hooks); custom-SVG `Gantt`, `DependencyGraph`, `CpmTable` (critical path in rose,
  slack, today/deadline lines, keyboard-focusable, table alternative); 6-step create-project
  wizard with live CPM preview and D40 schedule-risk acknowledgement; plan page; My Projects +
  reason-collecting cancel dialog; `TagPicker`; routes/nav wired (`phase:4` flags dropped); new
  client screens registered in `e2e/screens.ts`. Added a `headers` option to the API client for
  `If-Match`. 267 frontend tests pass; coverage ≥70% on all four metrics; lint/types/build green.
- **Security review:** `docs/security-reviews/phase-04.md`, 0 unresolved high, no fixes needed
  (new surface reused the Phase 1–3 authz/RLS/schema patterns).
- **Next:** run `make gate PHASE=4` with the Docker stack up (regenerate visual baselines for the
  two new client screens if the visual step flags them), then commit/tag `phase-4` for the user to
  push.

### 2026-10-18 — Taeen (with Claude Code), Phase 3
- **Done:** Phase 3 plan approved (`docs/plans/phase-03.md`); migration 0004 (profiles, skills,
  files, portfolio, certificates, external reviews, question bank, timed attempts, skill
  evidence) with RLS, guard triggers and SECURITY DEFINER test functions; 8 skills and 128 seeded
  questions; upload pipeline (`app/uploads/`: signatures, polyglot/PDF checks, Pillow re-encode
  without EXIF/GPS, signed 5-minute links, Nginx `X-Accel-Redirect`); profile, portfolio,
  evidence, file and skill-test APIs; orphan-file cleanup and expired-attempt jobs; screens:
  Profile & portfolio (autosave, drag reorder, dropzone), Skill challenges, timed test, public
  profile `/d/:id`, client organisation in Settings; real dashboard checklist.
- **Security review:** `docs/security-reviews/phase-03.md`, 0 unresolved high, 6 findings fixed
  (definer `is_system()` pitfall, self-verification guard, unverified clients, PDF escapes,
  parallel starts, upload volume permissions).
- **Also fixed:** sign-out race (guard redirected to /login before navigating home), visibility
  PATCH 500, autosave retry loop, coverage measurement under greenlets. Decisions D29–D37.
- **Gate:** first run failed on lint/types in a script; second run PASS.
- **Next:** hand-off for Phases 4–5; question-bank review by a team member.

### 2026-10-17 — Taeen (with Claude Code), Phase 2
- **Done:** Phase 2 plan approved (`docs/plans/phase-02.md`); design tokens (light/dark), theme
  and reduced-motion providers, motion system + lint rule; component library on Radix; role
  shells (sidebar, tab bar, command palette, toasts, offline/error/coming-soon pages); homepage
  per §13.11 with the 3D talent constellation (slim three entry, poster first, fallbacks),
  stills and social preview; auth screens restyled with password rules up front;
  `/public/stats`, `/client-errors`, migration 0003; `devsync-ui` skill; UI kit (dev only).
- **Security review:** `docs/security-reviews/phase-02.md`, 0 unresolved high, 5 findings fixed
  (Zod eval under CSP, Radix styles via a per-response nonce, `.dockerignore` keeping `.env` out
  of build contexts, …).
- **Gate:** several passes. Performance work from Lighthouse (desktop 78 → 97, mobile 60 → 96),
  responsive-matrix fixes, the 60 fps check moved to the laptop GPU. Decisions D21–D28.
- **Next:** manual testing of Phases 0–2 by the student; then Phase 3 in Plan Mode.
- **Blockers:** none.
### 2026-10-17 — Taeen (with Claude Code), Phase 1
- **Done:** Phase 1 plan approved (`docs/plans/phase-01.md`); migration 0002 (identity tables,
  RLS ENABLE+FORCE on every table, SECURITY DEFINER pre-auth functions, settings v2 with rate
  limits); Argon2id + breached list + zxcvbn; rotating server-side sessions; CSRF; Redis rate
  limits; ALTCHA CAPTCHA + honeypot + fill time; lockout; admin TOTP, recovery codes, step-up;
  deny-by-default authz with route × role matrix; outbox email + lifecycle jobs; frontend auth
  screens (login, admin TOTP, register, verify, forgot/reset, settings, role homes) with guards.
- **Security review:** `docs/security-reviews/phase-01.md`, 0 unresolved high, 7 findings fixed.
- **Gate:** three passes. Fixes: narrower semgrep rule, timing test with interleaved medians,
  typographic apostrophes in UI copy, forms wait out the 2 s minimum fill time instead of
  failing (fast password-manager users), smoke test ignores the expected anonymous `/me` 401.
  DECISIONS D19–D20.
- **Next:** Phase 2 in Plan Mode.
- **Blockers:** none.
### 2026-10-17 — Taeen (with Claude Code)
- **Done:** repository cloned; spec, paper and proposal studied; Phase 0 plan approved
  (`docs/plans/phase-00.md`); backend core (config, logging, errors, middleware, health,
  metrics, money, clock), migration 0001 (settings, hash-chained append-only audit log,
  jobs, idempotency keys), platform settings schema/service, RQ worker + scheduler, gate and
  checker scripts, Nginx/Compose/Postgres roles, frontend scaffold with tokens, docs, CI.
- **Gate:** four passes; fixes recorded in DECISIONS D15–D18 (frontend toolchain CVEs, Nginx
  host allowlist, SHA-pinned actions, Trivy DB source, Nginx 1.30/trixie base). Docker moved
  from the snap to Docker's apt packages (D17). Design skills installed after review (D14).
- **Next:** Phase 1 in Plan Mode.
- **Blockers:** none.
