# Architecture

See spec §5 for the runtime topology diagram. Services: Nginx (edge + load balancer),
API replicas (Gunicorn + Uvicorn), RQ workers, an APScheduler scheduler that only enqueues,
PostgreSQL 16, Redis 7, Judge0 (Phase 13, isolated `sandbox` network), Mailpit in development.
Networks: `edge` (nginx), `app` (nginx, api, worker, scheduler, redis, postgres), `sandbox`
(worker ↔ judge0, internal). Only Nginx publishes ports.

## Backend layering (strict, checked by `scripts/check_layers.py`)
`api` (HTTP only) → `services` (rules, transactions, authorization, audit) → `repositories`
(queries) → `models`. `algorithms` are pure and called only from services and jobs;
`integrations` are called through interfaces with fakes for tests.

## Key design decisions (spec §5.3)
1. **Opaque server-side sessions, not JWT in the browser.** Session id in an
   `HttpOnly; Secure; SameSite=Lax` cookie; session data in Redis with a DB record for
   revocation/listing. Simple revocation, no token theft via XSS storage.
2. **CSRF double-submit token** for all state-changing requests.
3. **Heavy work is asynchronous:** PSO runs, explanations, reputation updates, integrity
   scans, GitHub sync and emails run in RQ workers; the API returns `202` + job id.
4. **Stateless API replicas** behind Nginx `least_conn`; all shared state in Postgres/Redis.
5. **Money uses a double-entry ledger** with constraints that keep the books balanced.
6. **Pure algorithms** for testability and paper alignment.
7. **Polling + SSE, no WebSockets:** less attack surface.
8. **Self-hosted everything** (fonts, icons, libraries): strict CSP with no third-party origins.

## Phase 0 specifics
- Middleware order (§14.10): request id → trusted host → body limit (256 KB) → security
  headers → [session, CSRF, rate limit: Phase 1] → timeout (10 s) → router → exception
  handling (an in-chain safety net turns unknown errors into a generic 500 with request id).
- The audit log is append-only and hash-chained by database triggers (DECISIONS D12).
- Platform settings are immutable versions validated by `app/schemas/platform_settings.py`.
