# DevSync progress

## Current state
- **Current owner:** Salwa Baki (backend developer), Phases 4–5, from 2026-10-18 (hand-off from Mashfikuzzaman Taeen: `docs/handoffs/handoff-01-taeen-to-salwa.md`)
- **Current phase:** 3 — Profiles, portfolio, files, skill tests
- **Last gate result:** `PHASE 3 GATE: PASS` (2026-10-18; backend 640 tests, 95.4% coverage, security suite 219; frontend 244 tests, 72% coverage; E2E 40 + edge 13; 94 visual baselines; Lighthouse desktop 97 / mobile 96; 60 fps on the GPU)
- **In progress:** nothing; Phase 3 complete, tagged `phase-3` and pushed (`main`, `phase-3`)
- **Very next step:** Salwa: hand-off meeting, run the stack from scratch and confirm `make gate PHASE=3` passes on Salwa’s laptop, then start Phase 4 (projects and the CPM planner) in Plan Mode. Demo 1 is Mon 2 Nov 2026 (Phases 0–5).
- **Open human tasks:** review the 128 drafted test questions for accuracy (D34); tester's human check of the Phase 3 security review

## Phase table
| Phase | Owner | Status | Gate | Date | Tag |
|---|---|---|---|---|---|
| 0 Foundations | Taeen | done | PASS | 2026-10-17 | phase-0 |
| 1 Accounts & security core | Taeen | done | PASS | 2026-10-17 | phase-1 |
| 2 Design system & landing | Taeen | done | PASS | 2026-10-17 | phase-2 |
| 3 Profiles & skill tests | Taeen | done | PASS | 2026-10-18 | phase-3 |
| 4 Projects & CPM | Salwa | not started | — | — | — |
| 5 Marketplace & filtering | Salwa | not started | — | — | — |
| 6–15 | — | not started | — | — | — |

## Gate log (newest first, appended by `make gate`)
| Finished (UTC) | Phase | Result | Tests |
|---|---|---|---|
<!-- gate-log -->
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

## Session log (newest first)
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
