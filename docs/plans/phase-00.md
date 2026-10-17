# Phase 0 — Foundations, tooling, infrastructure (plan)

## Context
DevSync is being built from `DEVSYNC_BUILD_SPEC (3).md` (authoritative), implementing the [PCS] paper (`faircrowd_research_paper_palash_sir.pdf`) for CSE 3102. The repo is empty. Phase 0 (§17 "Phase 0") produces an empty but production-shaped system: containers, Nginx with TLS + headers, DB roles, migrations, platform settings, logging, CI and the phase gate — all green. Outcome: `make gate PHASE=0` prints `PHASE 0 GATE: PASS`, then commit `phase-0: …` + tag `phase-0` **locally only** (no push — user decision).

Skills loaded for this plan: none needed for backend/infra; frontend work in Phase 0 loads `frontend-design` once it is installed (step 11), per §0.4 rule 1.

## Environment facts (checked)
Docker 29 + Compose v5 OK · host Python 3.13 (no 3.12) · uv 0.13 · Node 20.18 / npm 9 · make · openssl · **no mkcert, no pip-compile, no gitleaks/semgrep/trivy on host** · 16 CPUs but **6.9 GB RAM (≈0.8 GB free)** · **23 GB disk free (96% used)**.
Consequences: everything Python runs in a `python:3.12-slim` container (parity for teammates); security scanners run from pinned Docker images; dev overrides Gunicorn workers to 2 (the `2×CPU+1` formula = 33 workers would exhaust RAM); Playwright runs in the official Playwright image (no host browser installs).

## Step 0 — repo housekeeping
- `git mv`-equivalent: rename spec → `DEVSYNC_BUILD_SPEC.md`; paper → `docs/papers/akter2023-pcs.pdf`; proposal → `docs/design/DevSync_Proposal_final.pdf`.
- Work on branch `phase-0`; merge to `main` + tag at the end.
- Save this plan as `docs/plans/phase-00.md`.

## Build — repository & docs (§4, §0.3, §0.5)
- Full §4 tree with placeholder READMEs/docstrings; `.gitignore` (`.env`, certs, `runs/*` except README, uploads, node_modules, dist).
- `CLAUDE.md` (≤60 lines: rules from §0, commands, spec pointer, session start/end routine).
- `PROGRESS.md` (Current state, phase table, session log), `DECISIONS.md`, `docs/OWNERSHIP.md`, `docs/BACKLOG.md`, `docs/sprints/sprint-01.md`, `docs/ARCHITECTURE.md` (§5.3 copied), stubs for `SECURITY.md`, `TESTING.md`, `API.md`, `FR_MAPPING.md` (proposal IDs listed; spec-side mapping filled per phase), `docs/security-reviews/`, `runs/README.md`, `.phase` = `none`.

## Build — backend (`backend/`)
1. `pyproject.toml`: ruff (rules E,F,W,I,B,UP,S,SIM,C4,RUF,ASYNC,PL,PT,N), mypy (strict for core/algorithms; `disallow_untyped_defs` everywhere), pytest markers (`--strict-markers`: unit, property, integration, api, fuzz, security, jobs, perf, chaos, edge, a11y), coverage (branch), bandit.
2. Lock files `requirements.lock` / `requirements-dev.lock` with hashes via `uv pip compile --generate-hashes` (pip-compile-compatible output). Runtime deps for P0 only: fastapi, pydantic v2, pydantic-settings, uvicorn, gunicorn, sqlalchemy[asyncio] 2, asyncpg, alembic, psycopg (sync, Alembic only), redis, rq, apscheduler 3, structlog, prometheus-client, httpx. Exact versions pinned at lock time.
3. `Dockerfile` (multi-stage, python:3.12-slim pinned by digest): `runtime` target (non-root uid 10001, read-only-fs friendly) and `dev` target (+dev deps) used by the gate/tests.
4. `app/core/config.py`: every §6.1 variable via pydantic-settings; `validate_production()` refuses to start in `production` on weak/short `SECRET_KEY`, `SMS_PROVIDER=console`, debug on, non-https `PUBLIC_ORIGIN`, Redis without password, `*` in `ALLOWED_HOSTS`, insecure cookies — prints each failure.
5. `app/core/logging.py`: structlog JSON, request-id contextvar, redaction processor (key regex `password|token|secret|otp|code|session|authorization|cookie|totp|phone`, value patterns, partial email masking).
6. `app/core/errors.py`: `ErrorCode` enum, `DomainError` hierarchy (incl. `InvalidStateTransition` → 409 `INVALID_STATE`), handler producing `{"error":{code,message,fields?,request_id}}`; unknown exceptions → generic 500 with request id only.
7. `app/core/clock.py` (injectable clock); `app/core/money.py` skeleton (Decimal context prec 28, ROUND_HALF_EVEN; `to_paisa(value, rounding)`), no floats.
8. `app/db/`: async engine/session dependency (statement_timeout 5 s app / 30 s jobs, pool from env), declarative `Base` with naming conventions, timestamp mixin, soft-delete mixin.
9. `app/schemas/common.py`: `ErrorResponse`, `ValidationErrorResponse`, `Page[T]`, `JobAccepted`, `StateTransitionError` (contract-first §10.4).
10. `app/main.py` app factory with middleware order §14.10 (request id → trusted host → body-size limit 256 KB → security headers → [session/CSRF/rate-limit slots, no-ops until Phase 1] → timeout guard 10 s → routers → exception handlers); `/api/v1/health` (liveness), `/api/v1/health/ready` (DB + Redis + queue), `/metrics` (Prometheus; blocked at Nginx); docs/OpenAPI only in development.
11. Alembic using `MIGRATION_DATABASE_URL`; migration `0001`: `pgcrypto`/`citext` extensions; tables `platform_settings`, `audit_log`, `jobs`, `idempotency_keys` (§7.1, §7.8); `audit_log` BEFORE INSERT trigger computing `prev_hash` and `hash = sha256(prev_hash ‖ canonical jsonb text)` under an advisory lock, BEFORE UPDATE/DELETE trigger that raises; SQL `audit_verify_chain()`; grants (app role: no UPDATE/DELETE on audit_log); seed settings v1.
12. Platform settings: `app/schemas/platform_settings.py` (typed model of all §6.2 keys, decimals as strings, validators: κ_e, κ_x > 0.5; α_x, α_e < 0.5; w_y + w_x = 1 with w_y > w_x; g sums 1; ranges) and `app/services/platform_settings.py` (load active version, `create_version()` validated → new row + audit entry). Adds keys the spec uses but §6.2 omits: `rep.newcomer_review`, `algorithm.mode`, `filter.newcomer_competency_check`, `filter.shortlist_min` (=6), `fitness.include_performance`, `fitness.use_skill_competency`.
13. `app/jobs/`: RQ worker entrypoint (`--max-jobs 500`, queues high/default/low), APScheduler scheduler container that enqueues a `ping` job; graceful SIGTERM handling.
14. `infra/postgres/init/`: shell init creating `devsync_migrator` (owner/DDL), `devsync_app` (DML), `devsync_worker` (DML, for jobs — §14.15), `devsync_readonly`; passwords from env; default privileges set so new tables grant correctly.
15. Scripts: `scripts/phase_gate.py` (stdlib only, runs on host; all 20 §16.5 steps — steps for parts that don't exist yet report `N/A (phase < k)` with the reason; writes `runs/gates/phase-0.json`, appends to PROGRESS.md, writes `.phase`), `scripts/check_forbidden.py` (§16.7, all Python/TS/repo patterns + `forbidden-ok` exceptions listed), `scripts/check_layers.py` (AST import rules §5.2), `scripts/check_rls.py` (implemented now; enforced from Phase 1), `scripts/check_openapi.py` (§10.4 linter, applied to existing routes), `runs/gates/baseline.json` creation.

## Build — infra
- `infra/nginx/nginx.conf` + `security-headers.conf`: TLS 1.2/1.3 only, 80→443 301, HSTS, exact §14.3 CSP + all headers, `server_tokens off`, `limit_req` zones (20 r/s burst 40 `/api/`, 5 r/s `/api/v1/auth/`), body limits (1m, 25m upload placeholder), all §15.3 timeouts, gzip + brotli (ngx_brotli dynamic module built in a builder stage against the same nginx version), upstream `api` `least_conn` + passive health checks + keepalive, SPA static with immutable `/assets/*` and `no-cache` index.html, internal file location placeholder, `/metrics` and `/api/v1/health/ready` denied externally, TRACE (and non-allowed methods) → 405, `ADMIN_ALLOWED_CIDRS` include hook.
- Compose: `docker-compose.yml` (nginx, api, worker, scheduler, postgres:16, redis:7; networks `edge`/`app`/`sandbox`; only nginx publishes ports; healthchecks; non-root; `read_only` + tmpfs; `no-new-privileges`; `cap_drop: ALL`), `.dev.yml` (hot reload, Mailpit, exposed dev ports, 2 workers), `.test.yml` (tmpfs Postgres/Redis, `dev` image test runner service), `.prod.yml` (replicas, §15.4 memory limits). Judge0 only as `infra/judge0/judge0.conf` placeholder (service arrives Phase 13).
- `Makefile`: all §16.6 targets; P0-functional ones: `env` (strong secrets via `secrets`), `certs` (mkcert if present, else openssl self-signed — documented), `up/down/logs`, `migrate`, `test`, `test-unit`, `test-backend`, `test-frontend`, `e2e`, `a11y`, `security`, `gate`; future ones print "available from Phase N".
- `.env.example` with every variable, safe dev defaults and comments.
- `.pre-commit-config.yaml` (ruff, ruff-format, prettier, eslint, gitleaks, check_forbidden); `.github/workflows/ci.yml` (push/PR: build with cache, `make gate PHASE=$(cat .phase)`, upload artifacts; nightly skeleton); `.github/dependabot.yml` (pip, npm, docker, actions weekly); `infra/semgrep/devsync.yml` custom rules.
- Security scanners as pinned images: gitleaks, semgrep, trivy; Bandit/pip-audit in the `dev` image; `npm audit` on host.

## Build — frontend (`frontend/`)
Vite 5 + React 18 + TS strict; Tailwind 3 with §13.1 tokens (light + dark CSS variables in `src/design/tokens.css`, mirrored in `tailwind.config.ts`, `src/design/tokens.ts` export); Inter + JetBrains Mono via `@fontsource`; placeholder page (one `h1`, skip link, DevSync wordmark); ESLint (typescript-eslint, react, jsx-a11y, security) + Prettier; Vitest + RTL + MSW setup; `design/contrast.test.ts` (every token pair ≥ 4.5:1, both themes); `tests/build/no-inline.test.ts` parsing `dist/index.html` (no inline scripts/styles, no external URLs); production build with `sourcemap: "hidden"`; Playwright config (chromium, firefox, webkit, mobile) + `e2e/smoke.spec.ts` loading `/` through Nginx (ignoreHTTPSErrors, asserts headers, no console errors, no off-origin requests, CSP violation listener).

## Skills (§0.4, step 11)
Clone `anthropics/skills` (frontend-design) and `CloudAI-X/threejs-skills` into a scratch dir, read every `SKILL.md` and script, reject anything that downloads code at runtime/needs keys/changes security settings, copy approved folders to `.claude/skills/`, write `.claude/skills/README.md` (source, commit hash, purpose) and record commit hashes in DECISIONS.md. I'll show you the review summary before committing them.

## Security (§14.13 row 0)
Dependabot + update policy; `/security-review` run at phase end → `docs/security-reviews/phase-00.md` (high/medium fixed or justified); secure config validation; secrets only via env; gitleaks/Bandit/Semgrep/pip-audit/npm audit/Trivy in the gate; non-root containers; Nginx TLS, redirect, headers, body limits, timeouts; forbidden-pattern scanner; layer checker.

## Tests (by layer)
- unit: config defaults/overrides/each insecure production combo refused; redaction (password/token/otp/session/phone values masked, nested dicts); error handler (no trace, request id present, domain codes map to statuses); money helpers; settings validation (each invalid rule rejected, defaults valid); clock; scripts (`check_forbidden` detects each pattern + honours `forbidden-ok`; `check_layers` flags a bad import) — all with failure/boundary cases.
- integration (test compose Postgres/Redis): migration up/down/up; audit_log UPDATE/DELETE raise; hash chain verifies and detects a tampered row (done as migrator); app role lacks UPDATE/DELETE grant; settings version insert + audit entry.
- api: `/health` 200; `/health/ready` 200 and 503 when Redis/DB unavailable; unknown host → 400; oversize body → 413; security headers on API responses.
- jobs: `ping` job via RQ SimpleWorker.
- edge (pytest against running stack from a container): HTTP→HTTPS 301; exact CSP + HSTS/nosniff/etc.; no `Server` version; TRACE → 405; >1 MB body → 413; `/metrics` and `/health/ready` not reachable via Nginx; `/api/v1/health` 200.
- frontend: contrast, no-inline build, placeholder render + axe; Playwright smoke (Chromium).
Coverage thresholds P0: backend 75%, frontend 60%.

## Decisions to record in DECISIONS.md (deviations/resolutions)
D1 `uv pip compile --generate-hashes` instead of pip-compile. D2 integration tests use the test-compose Postgres/Redis instead of testcontainers (no Docker socket in containers; same on every laptop/CI). D3 `make certs` falls back to openssl when mkcert is absent (mkcert required before Demo 1 for phone testing). D4 scanners via pinned Docker images. D5 dev Gunicorn workers = 2 (RAM). D6 shortlist size: §9.2 per-slot `max(3·count, 6)` wins over §6.2 text. D7 logout → `/` (§13.4/§13.11) over §15.5. D8 added missing settings keys + `devsync_worker` role. D9 Paper-vs-spec findings (A3 "−1", Algorithm 1 argmin, BPSO init, Eq. 21 on-time, "c" in Eq. 22) logged as open items for Phases 6/7/10 and §23.

## Gate checks (P0) & verification
1. `make env certs up && make migrate` → all containers healthy.
2. `curl -k -I https://localhost/api/v1/health` → 200 with exact headers; `curl -I http://localhost` → 301.
3. `make gate PHASE=0` → every applicable step PASS, prints `PHASE 0 GATE: PASS`, writes `runs/gates/phase-0.json`, `.phase` = 0.
4. Manual (you): open `https://localhost` → placeholder with Inter font, no console errors, no external requests in DevTools.
Then: update PROGRESS.md, commit `phase-0: foundations, tooling, infrastructure`, tag `phase-0` locally, stop and report (what was built, how to try it, what to check by hand, gate table).

## Risks
Disk (23 GB free; images + Playwright image ≈ 4–5 GB) and RAM (≈0.8 GB free) — I'll prune nothing of yours; if builds fail for space I'll stop and ask. ngx_brotli build complexity — fallback gzip_static + DECISIONS entry. Third-party skills may be rejected in review (then documented, not installed).
