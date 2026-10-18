# Hand-off 01 — Mashfikuzzaman Taeen → Salwa Baki

- **Date:** 2026-10-18
- **Outgoing:** Mashfikuzzaman Taeen (team leader), Phases 0–3
- **Incoming:** Salwa Baki (backend developer), Phases 4–5
- **Template:** spec §0.5. Both people review this document in the hand-off meeting.

## 1. Summary

Phases 0, 1, 2 and 3 are complete. Each gate printed `PHASE N GATE: PASS`, each has a security
review with 0 unresolved high findings, and each is tagged and pushed.

- **Work stops exactly at:** the end of Phase 3. Tag `phase-3` (commit `e825efc`) is on `main`
  and on branch `phase-3`. **Nothing of Phase 4 has been started**: no plan, no branch, no code.
- **Last passing gate:** `PHASE 3 GATE: PASS` on 2026-10-18.
- **Status:** the platform has secure accounts (phone OTP + email verification, admin TOTP,
  sessions, CSRF, rate limits, RLS, audit chain), the full design system and homepage with the
  3D hero, and developer/client profiles with portfolio uploads and timed skill tests.
- **Your job:** Phase 4 (projects and the CPM planner) and Phase 5 (marketplace, sealed bids,
  Algorithm 1 filtering). Phase 5 is the last phase before **Demo 1 on Mon 2 Nov 2026** (spec
  §17.0), so it also needs the Demo 1 readiness check.

## 2. How to run it from scratch

On a clean Linux laptop with Docker (docker-ce, not snap), Node 20, Python 3.12, `uv` and `make`:

```bash
git clone https://github.com/mashfikuzzaman-2023415968-cell/DevSync.git
cd DevSync
git checkout main            # = tag phase-3
make env                     # generates .env with your OWN random secrets (never commit it)
make certs                   # local TLS certificate for https://localhost
make up                      # builds and starts nginx, api, worker, scheduler, postgres, redis, mailpit
make migrate                 # alembic upgrade head (0001 → 0004)
make create-admin            # prompts for an admin email; prints the TOTP setup key and recovery codes once
```

- **Open:** https://localhost (the homepage). Mailpit, the local inbox for every email, is at
  http://127.0.0.1:8025.
- **Port 80 already taken** (e.g. by Apache): set `HTTP_PORT=8080` in `.env` and run
  `make up` again.
- **Accounts:** register through the UI.
  - SMS is simulated. The OTP appears in the API log:
    `docker compose -f docker-compose.yml -f docker-compose.dev.yml logs api | grep dev_sms`.
  - The verification email arrives in Mailpit.
  - There is no `make seed-demo` yet. **Building it (stage 1) is part of Phase 5** (spec §18.4).
- **Fast local test loop:**
  - Backend: `cd backend && uv venv --python 3.12 .venv && uv pip sync --python .venv/bin/python requirements.lock requirements-dev.lock && .venv/bin/pytest -m "unit"`.
  - Frontend: `cd frontend && npm ci && npx vitest run`.
- **Full gate:** `make gate PHASE=3` must print `PHASE 3 GATE: PASS` on your laptop before you
  start Phase 4 (hand-off procedure, step 3). It takes about 20–25 minutes. Step 16 needs a GPU
  (`/dev/dri`, D28).

## 3. What exists (by phase)

**Phase 0 — foundations:**
- Compose stack and Makefile.
- FastAPI skeleton with the §14.10 middleware chain.
- Settings (`app/core/config.py`) and platform settings (versioned, `app/schemas/platform_settings.py`).
- Integer-paisa money helpers (`app/core/money.py`) and the injectable clock (`app/core/clock.py`).
- Audit log with a hash chain (`app/core/audit.py`).
- RQ jobs, scheduler and worker (`app/jobs/`).
- Nginx edge with a strict CSP (`infra/nginx/`).
- The gate (`backend/scripts/phase_gate.py`) and the checkers (`check_forbidden.py`, `check_layers.py`, `check_openapi.py`, `check_rls.py`).
- Migration `0001`.

**Phase 1 — accounts and security core:**
- Users, sessions, OTP, email tokens, TOTP and recovery codes (`app/models/identity.py`).
- RLS on every table with SECURITY DEFINER pre-auth functions (migration `0002`).
- Auth services (`app/services/auth/`).
- Central authorization `authorize(principal, action, resource)` (`app/core/authz.py`).
- Rate limits (`app/core/ratelimit.py`), CSRF (`app/core/csrf.py`) and ALTCHA CAPTCHA.
- Routes in `app/api/v1/{auth,me,admin,captcha}.py`.
- Test-only seed router `app/api/v1/test_seed.py`, mounted only when `DEVSYNC_ENV=test`.

**Phase 2 — design system and homepage:**
- Tokens in `frontend/src/design/*` and the motion system in `design/motion.ts` (with a lint rule).
- Components in `frontend/src/components/ui/*` and role shells in `components/shell/*`.
- Router and guards in `frontend/src/app/*`.
- Homepage and 3D hero in `features/landing/*` and `components/three/*`.
- `/public/stats` and `/client-errors`, migration `0003`.
- The `devsync-ui` skill in `.claude/skills/devsync-ui/`.

**Phase 3 — profiles, files, skill tests (migration `0004_profiles_files_tests`):**
- **Tables:** `skills` (8, seeded), `developer_profiles`, `developer_skills`, `client_profiles`,
  `files`, `portfolio_items`, `portfolio_images`, `certificates`, `external_reviews`,
  `question_bank` (128 seeded questions), `skill_tests`, `test_attempts`, `skill_evidence`.
- **Uploads:** `app/uploads/` (detect, images, pipeline, signing, storage). Downloads go through
  `GET /files/{id}/download`, which redirects to a signed `/files/blob/{key}`, which Nginx serves
  with `X-Accel-Redirect`.
- **Services:** `app/services/{profiles,files,skill_tests,context}.py`, plus repositories and
  schemas with the same names.
- **Routes:** `app/api/v1/{profiles,files,skill_tests}.py`. The endpoint list is in `docs/API.md`
  ("Phase 3 endpoints").
- **Jobs:** `app/jobs/profile_jobs.py` (orphan-upload cleanup every hour, expired-attempt
  scoring every minute).
- **Screens:**
  - `/dev/profile` (autosave, drag reorder, dropzone)
  - `/dev/challenges` and `/dev/challenges/test/:attemptId`
  - public profile `/d/:id`
  - client organisation card in `/settings`
- **New UI components:** `FileDropzone`, `CountdownTimer`, `SortableList` (`@dnd-kit`).

## 4. Test and gate status

| Gate | Result | Backend | Frontend | Other |
|---|---|---|---|---|
| Phase 3 (2026-10-18) | PASS | 640 tests, 95.4% coverage; security suite 219 | 244 tests, 72% lines | E2E 40 + edge 13, axe clean, 94 visual baselines, Lighthouse desktop 97 / mobile 96, 60 fps on the GPU |

- There are no skipped or known-flaky tests.
- The sign-out redirect race that failed once in Phase 3 was fixed: `useLogout(all, leave)`
  navigates before clearing the session.
- Coverage thresholds rise in Phase 4: **backend 85%, frontend 70%** (Phases 4–9). Frontend is
  at 72% now, so new screens need their tests.

## 5. Known issues and limitations

- `make certs` makes a self-signed certificate. Install **mkcert** before Demo 1 (D3,
  `PROGRESS.md` known issues).
- Node 20 is end-of-life. The team should move to Node 22 LTS before Demo 1 (D15). Until then,
  use `npx -y npm@10.9.2 install …` for npm changes, because npm 9 has a resolver bug.
- The 128 skill-test questions were drafted by AI and **need a human accuracy review** (D34).
  Corrections go into a new seed version, never edits to v1.
- The tester's human check of the security reviews for Phases 0–3 is pending (Sara).
- Many `make` targets print "available from the phase that builds it". `seed-demo`, `erd`,
  `demo-check`, `demo-up`, `demo-reset` and `demo-preflight` are **yours to build** in
  Phases 4–5 (spec §16.6, §17.0, §18).

## 6. Open decisions and questions

- **Demo 1 risk rule (spec §17.0):** if time is short, skill tests and recommended projects may
  move to Demo 2. The CPM planner and sealed bidding with filtering never move. Decide with
  Taeen and record it in `DECISIONS.md`.
- **Answers still awaited:** none from the supervisor. Next decision number: **D38**.

## 7. Things Phases 4–5 depend on (don't change without care)

- **The phase workflow:**
  - Plan Mode, then `docs/plans/phase-04.md`, then approval.
  - Build, then `/security-review` into `docs/security-reviews/phase-04.md`.
  - `make gate PHASE=4` must print PASS.
  - Update `PROGRESS.md`, commit `phase-4: …`, tag `phase-4`, push.
- **The gate script needs your additions:**
  - `phase4_checks` and `phase5_checks` in `backend/scripts/phase_gate.py`. Without them,
    step 18 fails with "no PHASE_CHECKS defined".
  - From Phase 4 the gate also runs `pytest -m perf` (CPM: 300 milestones < 50 ms).
  - For Phase 5 (a demo phase), E2E runs on chromium, firefox, webkit and mobile, three times
    (`DEMO_PHASES`).
- **Every new table** needs ENABLE + FORCE RLS with policies in its migration, or an entry with
  a reason in `backend/app/db/rls_exempt.yml`. `check_rls.py` and the gate enforce this.
  Cross-user reads go through SECURITY DEFINER functions with `SET search_path = pg_catalog,
  public`, with EXECUTE revoked from PUBLIC. **Inside a definer, use `caller_is_system()`, not
  `is_system()`** (D36).
- **Every new route** needs:
  - an `authz` policy (deny by default);
  - an entry in `tests/security/test_authz_matrix.py` `MATRIX`;
  - an OpenAPI example for each success response, and declared 401/403/404 (+422 with a body or
    parameters);
  - a regenerated `docs/api/openapi.json` (`make openapi`) and `frontend/src/api/schema.d.ts`
    (`npm run api:types`).

  Public routes go in `PUBLIC_OPERATIONS` in `scripts/check_openapi.py`.
- **Layers:** `api → services → repositories → models`. `algorithms/` is pure: no DB, web,
  clock or network; seeded RNG; typed. `check_layers.py` enforces it. **CPM, forecast,
  filtering and `newcomer_snapshot()` all live in `backend/app/algorithms/`.**
- **Services take a `Ctx`** (`app/services/context.py`: db, settings, principal, now), built in
  routes with `Depends(acting("<policy>"))` from `app/api/deps.py`.
- **Money is integer paisa end to end.** Budgets, bonus pools and bid amounts use
  `app/core/money.py`, never floats, including in the frontend.
- **`skill_evidence`** (user, skill, source TEST, score 0–1, at) is the verified evidence that
  the Phase 5 newcomer rule reads. Read it through a service; don't query `test_attempts`.
- **Public profile data** comes only from `public_developer_profile()`. Never add email or phone
  to it.
- **Frontend:**
  - Load `devsync-ui` + `frontend-design` before any screen.
  - Data hooks live in `features/*/api.ts` and forms use RHF + Zod (`z.config({ jitless: true })`
    via `features/auth/schemas`).
  - Every screen needs all four states (loading, empty, error, success).
  - Add new screens to `frontend/e2e/screens.ts` (CSP, axe and responsive matrix) and to
    `e2e/visual.spec.ts`. Regenerate baselines with `make visual-update` and **look at them**.
  - Navigation entries with `phase: 4/5` in `src/app/navigation.ts` open a "coming soon" page
    until you replace them with real routes in `src/app/router.tsx`.

## 8. Gotchas

- **`.env` can't be `source`d with `set -a`** (the `EMAIL_FROM` line). Read single values with
  `grep '^NAME=' .env | cut -d= -f2-`.
- **Generating a migration** (autogenerate inside the backend image, with the code mounted):
  ```bash
  PW=$(grep '^DEVSYNC_MIGRATOR_PASSWORD=' .env | cut -d= -f2-)
  docker run --rm --network devsync_app --user $(id -u):$(id -g) -v $PWD/backend:/app -w /app \
    -e HOME=/tmp -e PYTHONPATH=/app \
    -e MIGRATION_DATABASE_URL="postgresql+psycopg://devsync_migrator:${PW}@postgres:5432/devsync" \
    devsync/backend:local alembic revision --autogenerate -m "..."
  ```
  Then add the RLS, definers and seed data by hand. Verify upgrade → downgrade → upgrade and
  `alembic check`.
- **The test stack bakes code into its images.** After backend changes, rebuild
  (`docker compose -p devsync-test -f docker-compose.yml -f docker-compose.test.yml build api
  tests`). For a fast loop, mount the code:
  `docker compose -p devsync-test … run --rm -T -e UPLOAD_DIR=/tmp/uploads -v $PWD/backend:/app tests pytest …`.
  After frontend changes, rebuild `nginx` before E2E.
- **Run the gate detached**, so closing the chat or terminal doesn't kill it:
  `systemd-run --user --unit=devsync-gate-p4 --working-directory=$PWD --setenv=PATH=$PATH --setenv=HOME=$HOME sh -c 'python3 backend/scripts/phase_gate.py --phase 4 --keep-going > runs/gate-phase4.log 2>&1; echo EXIT $? >> runs/gate-phase4.log'`.
- **New dependencies** must be named by the spec or recorded in DECISIONS, pinned exactly, and
  **at least 14 days old**. Python: `uv pip compile requirements.in --python-version 3.12
  --generate-hashes --exclude-newer <date 14+ days ago> -o requirements.lock`. npm:
  `npx -y npm@10.9.2 install --save-exact pkg@x.y.z`.
- **The forbidden-pattern scanner** rejects external URL literals, including `https://example.com`
  inside **OpenAPI examples**, because they land in `schema.d.ts`. Use `null` in examples.
- **SQLAlchemy:**
  - Assign enum members, not strings, to enum columns (a PATCH 500 came from this).
  - Re-read rows changed by definer functions with `.execution_options(populate_existing=True)`.
  - Coverage needs `concurrency = ["greenlet", "thread"]`; it's already set (D37).
- **FastAPI routes:** avoid paths that collide with `/{id}` routes. That's why reorder is
  `PUT /me/portfolio-order`, not `/me/portfolio/order`; schemathesis caught the collision.
- **MSW in Vitest:** within one `server.use(a, b)` call the earlier handler wins. Put
  overrides in a second `server.use(...)`.
- **E2E:** every request comes from one IP. Tests reset limits through `e2e/test.ts`, and long
  loops call `GET /api/v1/__test__/ratelimits/reset` (D27).
- **Git:** branches and tags have the same names (`phase-3`), so git warns "refname is
  ambiguous". Use `refs/heads/...` and `refs/tags/...` when pushing. Pushes use a GitHub token
  passed **per command**, never stored in git config or files.

## 9. Read first

1. `CLAUDE.md`, then the "Current state" in `PROGRESS.md`, then this document.
2. `DEVSYNC_BUILD_SPEC.md` §0–1 in full. Then §17 Phase 4 and Phase 5, and every section they
   reference: §7.3, §7.4, §7.7, §8, §9.0, §9.1.3, §9.2, §9.10, §9.16, §9.17, §9.19, §10, §13.5
   screens 6, 10–12, 21–23, 31, §14.5, §14.13 rows 4–5, §16.4, §16.5, §17.0, §18.
3. `DECISIONS.md`, all of it (D1–D37).
4. `docs/papers/akter2023-pcs.pdf`, Section 4.2 (Algorithm 1). §9 of the spec is authoritative
   for formulas.
5. `docs/plans/phase-03.md` and `docs/security-reviews/phase-03.md`, as worked examples of the
   expected depth.

## 10. Secrets and setup

- **Generate your own** with `make env`: `SECRET_KEY`, `CAPTCHA_HMAC_KEY`, database role
  passwords, `REDIS_PASSWORD`. Never commit `.env`.
- **Create your own admin** with `make create-admin`. Keep its TOTP key and recovery codes
  private.
- **The GitHub push token** is passed privately (never through git or chat logs that are
  committed). Use it per command:
  `git -c credential.helper= -c http.extraHeader="Authorization: Basic $(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)" push origin refs/heads/<branch> refs/tags/<tag>`.
- **Taeen's local accounts** (`~/devsync-local-accounts.txt`) exist only on Taeen’s laptop. Don’t
  expect them.
