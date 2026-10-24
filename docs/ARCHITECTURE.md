# Architecture

Current through **Phase 5** (Demo 1, 2 Nov 2026). Spec §5 is the authoritative design; this
file describes what is built, with file paths, and what later phases add.

- Diagram: [`design/architecture.svg`](design/architecture.svg) (containers and data flows)
- Use cases: [`design/use-cases.svg`](design/use-cases.svg) (built through Phase 5 vs later)
- Data model: [`design/erd.svg`](design/erd.svg) (generated from the models by `make erd`)
- Security model and threat table: [`SECURITY.md`](SECURITY.md)

## 1. Containers

All services are defined in `docker-compose.yml`; overlays change them per environment:
`docker-compose.dev.yml` (hot reload, Mailpit), `docker-compose.test.yml` (ephemeral data for
the gate and CI, test runner), `docker-compose.prod.yml` (3 API replicas, 2 workers, memory
limits). **Only Nginx publishes ports** (plus Mailpit on `127.0.0.1:8025` in development).

| Service | Image / entry point | Role |
|---|---|---|
| `nginx` | `infra/nginx/Dockerfile` (Brotli module build → Vite build of the SPA on Node 20 → `nginx-unprivileged`) | TLS edge (8443 → host 443, 8080 → 301 to HTTPS), static SPA, security headers, coarse rate limits, timeouts, `least_conn` load balancing to `api`, `X-Accel-Redirect` file delivery |
| `api` | `backend/Dockerfile` → `gunicorn -c gunicorn.conf.py app.main:app_factory()` | FastAPI on Gunicorn with Uvicorn workers (`2×CPU+1`, or `GUNICORN_WORKERS`; worker recycling after ~1,000 requests; 30 s timeout). The dev overlay runs `uvicorn --reload` instead |
| `worker` | `python -m app.jobs.worker` | RQ worker on queues `high` → `default` → `low`; restarts after 500 jobs; warm shutdown on SIGTERM |
| `scheduler` | `python -m app.jobs.scheduler` | APScheduler (timezone Asia/Dhaka) that **only enqueues** RQ jobs, so a restart never loses or duplicates work |
| `postgres` | `postgres:16` + `infra/postgres/init/01-roles.sh` | Data; four least-privilege roles, Row-Level Security on every table |
| `redis` | `redis:7-alpine` (password, AOF, 256 MB, `noeviction`) | Sessions, rate-limit windows, small caches, RQ queues |
| `mailpit` | `axllent/mailpit` (dev overlay only) | Catches all outgoing email in development and demos |
| `migrate` | backend image, profile `tools` | One-off `alembic upgrade head` as `devsync_migrator` |

Networks: `edge` (nginx), `app` (nginx, api, worker, scheduler, postgres, redis, mailpit) and
`sandbox` (`internal: true`, worker only for now; Judge0 joins it in Phase 13 with no route to
`app` or the internet). Every application container runs non-root with a read-only root
filesystem, `no-new-privileges`, all capabilities dropped and a `/tmp` tmpfs (`x-hardening`).
Uploaded files live in the `uploads` volume (read-write for api/worker, read-only for nginx).

`make up` and `make demo-up` both use the base + dev overlay (one API container). The
production overlay (`docker-compose.prod.yml`) is where replicas are defined; it is exercised
in Phase 14 (load and chaos) and Phase 15 (deployment).

## 2. Request path

```
browser ──HTTPS──▶ nginx ──HTTP (app network)──▶ api (Gunicorn/Uvicorn) ──▶ Postgres / Redis
                    │ /assets, /index.html, SPA fallback served from the image
                    └ /_protected_files/ (internal only, reached via X-Accel-Redirect)
```

**At Nginx** (`infra/nginx/nginx.conf`, `proxy-api.conf`, `security-headers.conf`): unknown
`Host` → 400; methods other than GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS → 405 (JSON body);
`/metrics` and `/api/v1/health/ready` → 404 from outside; per-IP `limit_req` (`/api/` 20 r/s
burst 40, `/api/v1/auth/` 5 r/s burst 10), 50 connections per IP; 1 MB bodies (25 MB on the four
upload routes); connect 3 s / read 30 s timeouts; one retry on another upstream for
connection errors, timeouts, 502 and 503. Each request gets `X-Request-ID`. `index.html` is
`no-store` and carries a fresh per-response style nonce (D23); hashed assets are immutable.
No upstream keepalive (D54: avoids 502s when Gunicorn recycles a worker).

**In the API** (`backend/app/main.py`, outermost first; spec §14.10):

1. Request id (`core/middleware.py`) — accepts Nginx's id or makes one, echoes it, binds it to logs
2. Trusted host (`ALLOWED_HOSTS`)
3. Body size limit — 256 KB JSON; larger only for POSTs to upload routes
4. Security headers (CSP, nosniff, `Cache-Control: no-store` on API responses, …)
5. Session load (`core/auth_middleware.py`, `core/sessions.py`) — `Principal` on `request.state`
6. CSRF for unsafe methods (`core/csrf.py`)
7. Global rate limit (`core/ratelimit.py`: 120/min per user, 60/min per IP); route scopes
   (login, registration, bids …) are dependencies in the routers
8. Timeout guard (10 s per route)
9. Router (`app/api/v1/*`)
10. Exception handling (`core/errors.py` + `UnhandledExceptionMiddleware`): domain errors map
    to `{error: {code, message, request_id}}`; unknown errors become a generic 500

A Prometheus `MetricsMiddleware` wraps the whole chain; `/metrics` is internal only.

## 3. Backend layering

`api` (HTTP only: dependencies, schemas, status codes) → `services` (business rules,
transactions, authorization calls, state transitions, audit) → `repositories` (queries) →
`models` (SQLAlchemy). `backend/scripts/check_layers.py` enforces the import rules in the gate.

- `app/algorithms/` is **pure** (no DB, web, network or clock): `cpm.py`, `forecast.py`
  (Phase 4), `filtering.py` (Algorithm 1 + newcomer rule + relaxation + shortlist, explanations,
  cheapest team), `reputation.py` (newcomer snapshot), `availability.py` (Phase 5). Called only
  from services and jobs; covered by `tests/algorithms` and `tests/property`.
- `app/schemas/` — Pydantic models with `extra="forbid"` (mass assignment → 422).
- `app/uploads/` — the upload pipeline (signature detection, polyglot/PDF checks, Pillow
  re-encode, HMAC-signed URLs, storage with random keys).
- `app/integrations/` — `email.py` (templates, SMTP), `sms.py` (`console` in development only,
  `noop` in tests). Phase 13 adds GitHub and Judge0 behind interfaces with fakes.
- `app/core/` — config (refuses insecure production settings), logging with redaction, errors,
  security (Argon2id, zxcvbn, breached list, TOTP), sessions, CSRF, CAPTCHA (ALTCHA), rate
  limits, authz, audit, money (`Decimal` → integer paisa), clock, redirects, metrics.
- `app/db/` — engines (app and worker roles, per-connection timeouts) and the RLS context.

## 4. Identity, sessions, CSRF and authorization

- **Sessions** (`core/sessions.py`): an opaque 256-bit token in `__Host-ds_session`
  (HttpOnly, Secure, SameSite=Lax). The server keeps only its SHA-256, in Redis (fast path)
  and the `sessions` table (listing, revocation, recovery). Rotated after 15 minutes with a
  30-second grace window; idle 30 min (15 for admins); absolute 7 days; rotated on login,
  privilege change and step-up. "Sign out of every device" and per-device sign-out exist.
- **CSRF** (`core/csrf.py`): double submit — `GET /auth/csrf` sets `__Host-ds_csrf`
  (bound to the session by HMAC) and echoes the token in a header (D53); every unsafe `/api/`
  request needs a matching `X-CSRF-Token` and an `Origin`/`Referer` equal to `PUBLIC_ORIGIN`.
- **Admins** must enrol TOTP (secret AES-GCM encrypted), get 10 recovery codes and use
  step-up for sensitive actions. The admin area answers 404 to everyone else and ships as a
  separate frontend chunk loaded only after `/admin/session` confirms the session.
- **Authorization** (`core/authz.py`): `authorize(principal, action, resource)`, deny by
  default. No session → 401, wrong role → 403, not your object → 404. Every route × role is
  pinned by `tests/security/test_authz_matrix.py`.
- **Row-Level Security** (second gate, spec §14.15): every transaction starts with
  transaction-local `set_config('app.user_id' / 'app.role')` from the server-side session
  (`db/context.py`); without it the role is GUEST and user policies match nothing. Tables are
  owned by `devsync_migrator`; `devsync_app` (web, DML only, 5 s statement timeout) and
  `devsync_worker` (jobs, role SYSTEM, 30 s) have no `BYPASSRLS`; every table has ENABLE +
  FORCE RLS (`scripts/check_rls.py`). Pre-authentication look-ups, test scoring, file access,
  public stats and project visibility go through `SECURITY DEFINER` functions with a pinned
  `search_path`. Sealed bids are enforced here too (Phase 5).
- **Audit log** (`core/audit.py`): insert-only; a database trigger hash-chains each row and
  blocks UPDATE/DELETE (D12).

## 5. Background jobs

RQ jobs reload their data and re-check permissions; they never trust the queue payload
(`jobs/tasks.py`). The scheduler (`jobs/scheduler.py`) enqueues:

| Job | Every | Queue | What it does |
|---|---|---|---|
| `ping` | 5 min | low | Heartbeat |
| `email.send` | 30 s | high | Delivers the transactional outbox (`email_outbox`, written in the business transaction) with backoff |
| `lifecycle.expire` | 5 min | low | Removes expired sessions, OTPs, email tokens, idempotency keys |
| `uploads.cleanup` | 1 h | low | Orphan and deleted uploads (§14.9) |
| `attempts.expire` | 1 min | default | Scores skill-test attempts whose deadline passed |
| `bidding.deadline` | 5 min | default | Closes bidding (→ FORMING, or too-few-bids notice), shortfall reminder at 7 days, auto-cancel at 14 days (D54) |

In-app notifications are written by SYSTEM sessions (`services/notifications.py`); the inbox
UI arrives in Phase 9.

## 6. Frontend

Vite + React 18 + TypeScript (strict), in `frontend/src`.

- **Routing** (`app/router.tsx`, React Router 7): every page is a lazy route with
  `handle.title`. Public pages (homepage, login, register, verify, reset, `/projects`,
  `/d/:id`, legal), developer pages under `/dev/*`, client pages under `/client/*`, shared
  `/settings`, and `admin/*`. Pages of later phases are registered from `app/navigation.ts`
  with a `phase` flag and show a "coming soon" page.
- **Guards** (`app/guards.tsx`): `RequireAuth` sends signed-out users to `/login?return_to=…`
  (validated by `lib/redirects.ts`), PENDING users to `/verify`, wrong roles to `/403`, admins
  without TOTP to `/admin/setup-2fa`. `AdminArea` loads the admin bundle only after the server
  confirms an admin session. Guards decide what to show; the server re-checks everything.
- **Data**: TanStack Query hooks per feature (`features/*/api.ts`) over one fetch wrapper
  (`api/client.ts`: same origin, CSRF header, `ApiError` with request id and `Retry-After`,
  offline event). Types are generated from the OpenAPI contract (`api/schema.d.ts`,
  `make openapi`). `app/queryClient.ts` turns 403/429 into toasts. Forms use React Hook Form +
  Zod schemas that mirror the backend.
- **Shells**: `RoleShell` → `components/shell/AppShell.tsx` (top bar, collapsible sidebar,
  bottom tab bar + More sheet on phones, Ctrl/⌘K command palette, toasts, offline banner).
- **Design system**: tokens in `design/tokens.css` (+ `tokens.ts`, contrast-tested), motion in
  `design/motion.ts`, theme and reduced-motion preferences in `design/preferences.tsx`,
  primitives in `components/ui/*` (Radix based), domain composites `Gantt`, `DependencyGraph`,
  `CpmTable`. See [`UI_GUIDE.md`](UI_GUIDE.md).
- **Homepage 3D hero**: `components/three/TalentConstellation.tsx` (React Three Fiber, slim
  `three` entry, poster first, fallbacks for reduced motion, no or software WebGL).
- **CSP**: no inline scripts or styles; runtime `<style>` tags (Radix scroll lock) use the
  per-response nonce from `<meta name="csp-nonce">` (`lib/nonce.ts`).
- Dev-only screens (`/dev/ui-kit`, `/__stills`) exist only when `DEV_TOOLS` is set at build time.

## 7. Data model

Seven migrations (`backend/alembic/versions/0001`–`0007`) create 36 tables, grouped as:

| Group | Tables | Phase |
|---|---|---|
| Foundation | `platform_settings` (immutable versions), `audit_log`, `jobs`, `idempotency_keys` | 0 |
| Identity | `users`, `sessions`, `otp_codes`, `email_tokens`, `totp_credentials`, `recovery_codes`, `devices_seen`, `notifications`, `email_outbox` | 1 |
| Profiles and tests | `skills`, `developer_profiles`, `developer_skills`, `client_profiles`, `files`, `portfolio_items`, `portfolio_images`, `certificates`, `external_reviews`, `question_bank`, `skill_tests`, `test_attempts`, `skill_evidence` | 3 |
| Projects and planning | `projects`, `project_slots`, `milestones`, `milestone_skills`, `milestone_dependencies`, `plan_baselines`, `plan_change_requests` | 4 |
| Bidding | `bids`, `availability_reservations`, `reputation_snapshots` (+ project search vector, bidding terms in 0007) | 5 |

Money is `BIGINT` paisa everywhere; times are `timestamptz` (UTC) and shown in Asia/Dhaka.
The ERD is regenerated from the SQLAlchemy models with `make erd` →
[`design/erd.svg`](design/erd.svg).

## 8. Key design decisions (spec §5.3)

1. **Opaque server-side sessions, not JWT in the browser** — simple revocation, nothing to steal from storage.
2. **CSRF double-submit token** plus an Origin check for every state-changing request.
3. **Heavy work is asynchronous** in RQ workers (emails and lifecycle jobs today; PSO runs, reputation updates, integrity scans and GitHub sync later), with `202` + job id.
4. **Stateless API replicas** behind Nginx `least_conn`; all shared state in Postgres/Redis.
5. **Money uses a double-entry ledger** whose entries always balance (Phase 10).
6. **Pure algorithms** for testability and paper alignment.
7. **Polling + SSE, no WebSockets** — less attack surface (SSE arrives in Phase 9).
8. **Self-hosted everything** (fonts, icons, 3D assets): a strict CSP with no third-party origins.

## 9. What later phases add

| Phase | Architectural additions |
|---|---|
| 6 | Reputation engine ([PCS] Eq. 1–12) writing `reputation_snapshots` (replacing the seeded values, D44/D48); market simulator |
| 7 | Formation runs as RQ jobs (BPSO, exact solver ≤ 18, fairness, explanations), job status polling, run quotas and idempotency |
| 8 | Invitations, team lead, team repair; availability re-checked on acceptance |
| 9 | Workspace tables, Kanban, check-ins, risk engine and forecasts, SSE (cookie auth + Origin), notification inbox |
| 10 | Double-entry ledger with `post_transaction()` (SECURITY DEFINER), escrow, payouts, idempotency keys in use |
| 11–12 | Blind reviews, integrity rules, disputes, the full admin console with step-up |
| 13 | GitHub evidence and Judge0 on the isolated `sandbox` network, webhook verification |
| 14 | Replicas under load (k6), chaos tests, PgBouncer and caching decisions, ZAP |
| 15 | Production deployment, backups and restore drill |
