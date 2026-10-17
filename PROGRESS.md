# DevSync progress

## Current state
- **Current owner:** Mashfikuzzaman Taeen (team leader)
- **Current phase:** 1 — Accounts, authentication, sessions, security core
- **Last gate result:** `PHASE 1 GATE: PASS` (2026-10-17; backend 417 tests, 87.7% coverage, security suite 71; frontend 132 tests, 86.3% lines; E2E 7)
- **In progress:** nothing; Phase 1 complete, tagged `phase-1` and pushed to GitHub (`main`, `phase-1`)
- **Very next step:** Phase 2 (design system & landing) in Plan Mode

## Phase table
| Phase | Owner | Status | Gate | Date | Tag |
|---|---|---|---|---|---|
| 0 Foundations | Taeen | done | PASS | 2026-10-17 | phase-0 |
| 1 Accounts & security core | Taeen | done | PASS | 2026-10-17 | phase-1 |
| 2 Design system & landing | — | not started | — | — | — |
| 3 Profiles & skill tests | — | not started | — | — | — |
| 4 Projects & CPM | — | not started | — | — | — |
| 5 Marketplace & filtering | — | not started | — | — | — |
| 6–15 | — | not started | — | — | — |

## Gate log (newest first, appended by `make gate`)
| Finished (UTC) | Phase | Result | Tests |
|---|---|---|---|
<!-- gate-log -->
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
- Tester's human check of `docs/security-reviews/phase-00.md` and `phase-01.md` is pending (Sara).
- Existing dev databases: run `make migrate` (migration 0002); create an admin with `make create-admin`.

## Session log (newest first)
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
