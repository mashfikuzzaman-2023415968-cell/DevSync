# Security

Written from spec §14; grows every phase (§14.13). Each control links to its tests.

## Threat model (STRIDE)

Assets (§14.1): accounts and sessions, personal data, sealed bids, project content and files,
reputation, admin powers, platform settings, the audit log and secrets (money, reviews and
disputes arrive in later phases). The table covers every component and data flow built through
Phase 5 (see [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`design/architecture.svg`](design/architecture.svg));
paths are relative to `backend/` unless they start with `frontend/` or `infra/`. Rows for
components that do not exist yet name the phase that adds them. Each control's tests are in the
"Controls implemented" tables below.

S = Spoofing, T = Tampering, R = Repudiation, I = Information disclosure, D = Denial of service,
E = Elevation of privilege.

### Edge and transport (browser ↔ Nginx ↔ API)

| | Threat | Mitigation as implemented | Residual risk |
|---|---|---|---|
| S | Host-header attacks, DNS rebinding | Nginx answers 400 to unknown hosts and proxies with `$server_name` (`infra/nginx/nginx.conf`); `TrustedHostMiddleware` with `ALLOWED_HOSTS` (`app/main.py`) | Production host names are set at deployment (Phase 15) |
| S | Spoofed client IP to dodge per-IP limits | Nginx overwrites `X-Forwarded-For` with `$remote_addr` (`infra/nginx/proxy-api.conf`); the app trusts it only from `TRUSTED_PROXY_IPS` (`app/core/netutil.py`, `gunicorn.conf.py`) | Many users behind one NAT share one IP budget (D53) |
| T | Traffic tampering, downgrade | TLS 1.2/1.3 only, modern ciphers, HTTP → 301, HSTS 1 year (`infra/nginx/nginx.conf`, `proxy-api.conf`) | Self-signed/mkcert certificates in development and demos (D3) |
| T | Clickjacking, injected content | `frame-ancestors 'none'`, exact CSP without `unsafe-inline`/`unsafe-eval`, per-response style nonce (`infra/nginx/security-headers.conf`, D23); API responses carry their own `default-src 'none'` CSP (`app/core/middleware.py`) | Nonce equals the Nginx request id, which appears in internal logs (accepted, Phase 2 review) |
| I | Caching of private responses; internal endpoints | `Cache-Control: no-store` on API responses and `index.html`; `/metrics` and `/api/v1/health/ready` → 404 at Nginx; docs/OpenAPI off in production (`app/main.py`) | — |
| I | Verbose errors | One error shape with a request id; unknown errors → generic 500, trace only in server logs (`app/core/errors.py`, `UnhandledExceptionMiddleware`) | — |
| D | Floods, slowloris, oversized bodies | `limit_req` 20 r/s (5 r/s on `/auth/`) and 50 connections per IP, 1 MB body (25 MB on upload routes), 15 s body timeout, 3 s connect / 30 s read (`infra/nginx/*.conf`); app body limit 256 KB JSON (`app/core/middleware.py`), 10 s route timeout, Gunicorn 30 s, global 120/min per user, 60/min per IP (`app/core/auth_middleware.py`) | No CDN or upstream DDoS protection (out of scope); load and chaos results come in Phase 14 |
| E | Unsupported methods (TRACE) | Method allowlist → 405 JSON (`infra/nginx/nginx.conf`) | — |

### Accounts, sessions and CSRF (Phase 1)

| | Threat | Mitigation as implemented | Residual risk |
|---|---|---|---|
| S | Credential stuffing, password guessing | Argon2id + rehash, zxcvbn ≥ 3, bundled breached list (`app/core/security.py`); login 5/min and 20/h per IP+email, progressive delay, 15-minute lock after 10 failures with an email notice (`app/services/auth/login.py`, `app/core/ratelimit.py`); ALTCHA CAPTCHA after failures and always for admins (`app/core/captcha.py`) | Lockout can be triggered by someone who knows the email (accepted, Phase 1 review) |
| S | Fake or duplicate accounts, bots | Phone OTP (hashed, 5 min, 5 attempts, 60 s resend) and one account per phone; email link (hashed, single use); CAPTCHA, honeypot, minimum fill time (`app/services/auth/registration.py`, `frontend/src/features/auth/Honeypot.tsx`) | SMS is simulated (`console` in development, `noop` in tests; config refuses `console` in production); a real provider arrives in Phase 15 |
| S | Session theft or fixation | Opaque 256-bit token in `__Host-ds_session` (HttpOnly, Secure, SameSite=Lax); only its SHA-256 stored; rotation every 15 min and on login/privilege change/step-up; idle 30 min (admins 15), absolute 7 days; logout-all and per-device sign-out (`app/core/sessions.py`, `app/core/auth_middleware.py`) | A stolen cookie works until rotation/idle expiry; new-device emails tell the user (`app/services/auth/login.py`) |
| S | Admin account takeover | Mandatory TOTP (AES-GCM secret, ±1 window, replay-proof `last_used_step`), 10 Argon2id recovery codes, step-up for sensitive actions (`app/services/auth/credentials.py`) | — |
| T | Cross-site request forgery | Double-submit `__Host-ds_csrf` bound to the session by HMAC + `X-CSRF-Token` + Origin/Referer = `PUBLIC_ORIGIN` on every unsafe request (`app/core/csrf.py`) | — |
| T | Open redirect after sign-in | `return_to` validated on server and client (`app/core/redirects.py`, `frontend/src/lib/redirects.ts`) | — |
| R | "I never changed my password / signed in" | Security events written to the hash-chained audit log with actor, IP and request id (`app/core/audit.py`, trigger in `alembic/versions/0001_foundation.py`) | Audit viewer and chain verification UI arrive in Phase 12 |
| I | Account enumeration | Uniform registration, login and reset responses; dummy hash for unknown users; timing tested (`app/services/auth/*`) | — |
| I | Secrets in logs | structlog redaction of keys and values (`app/core/logging.py`); auth bodies never logged | — |
| D | OTP/email flooding | OTP 1/60 s and 5/h per phone and IP; reset 3/h; email resend 3/h; auth scopes fail **closed** if Redis is down (`app/core/ratelimit.py`) | Redis outage blocks sign-in (by design) |

### Authorization and the database (all phases)

| | Threat | Mitigation as implemented | Residual risk |
|---|---|---|---|
| E | Missing or wrong permission check | Deny-by-default `authorize(principal, action, resource)`; 401/403/404 semantics (`app/core/authz.py`); route × role matrix test fails for any unlisted route | — |
| E | Buggy query returns other users' rows | RLS ENABLE + FORCE on every table, transaction-local `app.user_id`/`app.role` from the server session, fail closed as GUEST (`app/db/context.py`, migrations 0002–0007, `scripts/check_rls.py`) | SYSTEM sessions (worker role) see more by design; used only after the caller is authorised (D50) |
| E | Privilege via DB role | Roles without SUPERUSER/BYPASSRLS; app has DML only; migrator owns the schema; definer functions pin `search_path`, EXECUTE revoked from PUBLIC (`infra/postgres/init/01-roles.sh`, migrations) | — |
| E | Role or ownership tampering (mass assignment) | `extra="forbid"` schemas; server sets owner ids, roles, statuses, scores (`app/schemas/*`) | — |
| E | Admin area discovery | `/admin/*` answers 404 to non-admins; admin code in a separate chunk loaded only after `/admin/session` (`app/core/authz.py`, `frontend/src/app/guards.tsx`) | Optional `ADMIN_ALLOWED_CIDRS` allowlist not configured in development |
| T | Audit log rewriting | INSERT-only grants, UPDATE/DELETE blocked by trigger, hash chain (`alembic/versions/0001_foundation.py`, D12) | A database superuser could still rebuild the chain (host compromise is out of scope) |
| D | Slow queries holding connections | `statement_timeout` 5 s (app) / 30 s (worker), `lock_timeout`, `idle_in_transaction_session_timeout` (`app/db/session.py`, `01-roles.sh`) | — |

### Profiles, files and skill tests (Phase 3)

| | Threat | Mitigation as implemented | Residual risk |
|---|---|---|---|
| T | Malicious uploads (polyglots, active content, PDF actions, decompression bombs) | Type by signature with per-kind allowlists; polyglot, markup and PDF-action checks; Pillow re-encode under a pixel budget, EXIF/GPS stripped; streamed to a 0600 temp file under a size limit (`app/uploads/*`, D31) | ClamAV hook not enabled (`scan_status = SKIPPED`); rare false rejections of images (accepted) |
| T | Path traversal | Random UUID storage keys; names kept only as sanitised metadata (`app/uploads/storage.py`) | — |
| I | Reading someone else's file (IDOR) | Authorization in the `file_access` definer → 5-minute HMAC-signed URL → `X-Accel-Redirect` into an `internal` location with attachment, nosniff and sandbox CSP (`app/services/files.py`, `app/api/v1/files.py`, `infra/nginx/nginx.conf`, D32) | Anyone holding a signed link can use it for 5 minutes (accepted, D32) |
| I | Private profile data | No email/phone on public profiles; visibility setting enforced by `profile_visible` (clients-only profiles need a verified client) (migration 0004, `app/services/profiles.py`) | — |
| T | Self-verified certificates or skill evidence | Verification is admin-only in the service and a trigger (D35); evidence written only by definers | Admin verification screen arrives in Phase 12 |
| T/I | Cheating on timed tests | Correct answers never leave the DB (`attempt_questions`, `score_test_attempt`); server-side timer, late answers refused, one open attempt with an advisory lock, 30-day retake, 10 starts/h (`app/services/skill_tests.py`, D33) | Question quality depends on the human review of the 128 drafted questions (D34) |
| D | Storage exhaustion | 20 uploads/h, per-file size limits, orphan cleanup job (`app/jobs/profile_jobs.py`) | The §14.8 daily volume quota (500 MB/day) is not a separate rule yet; uploads are capped by count and file size |

### Projects and planning (Phase 4)

| | Threat | Mitigation as implemented | Residual risk |
|---|---|---|---|
| I | Reading another client's draft | RLS: drafts visible only to their client and admins; non-owners get 404 (`alembic/versions/0005_projects_planning.py`, `app/services/projects.py`) | — |
| T | Lost updates / blind overwrite | `If-Match` with the project version; stale write → 409 (`app/api/v1/projects.py`) | — |
| T | Publishing an invalid or unfunded plan; editing after publish | Publish guards in the service **and** a DB trigger (verified payment method, ≥ 1 slot, shares 100 %, acyclic, risk acknowledgement); baseline frozen by trigger (D39, D40) | Payment-method verification is simulated (D39) |
| D | Cyclic or huge plans | Cycle → 422 (never a hang); bounded milestones/dependencies; 300-milestone CPM < 50 ms (`app/algorithms/cpm.py`) | — |
| R | Disputed cancellations | Cancellation requires a reason (1–500 characters) and is audit-logged | — |

### Marketplace and sealed bidding (Phase 5)

| | Threat | Mitigation as implemented | Residual risk |
|---|---|---|---|
| I | Developers seeing others' bids | RLS on `bids`/`availability_reservations` (bidder, project client, admin only); `bid.view` vs `bid.read` actions; search and public lists never select bid columns (`alembic/versions/0006_marketplace_bidding.py`, `app/services/marketplace.py`) | Bid prices are visible to the client during bidding (spec), sealed from other developers |
| I | Leaking bidder data through eligibility | Eligibility computed in a SYSTEM session after the caller is authorised as owner; only verdicts returned; the developer's dry run never ranks against other bids (`app/services/bids.py`, D50, D54) | — |
| T | Late bids, bids on closed projects | Place/edit/withdraw/preview require BIDDING **and** `now < bidding_deadline` (409) (D54) | — |
| T | Bid spam, duplicate bids | One ACTIVE bid per developer (partial unique index, D49), 20 bid writes/h, mass assignment → 422 | — |
| T | Referencing someone else's portfolio | `portfolio_item_ids` must be the bidder's own (422) (D54) | — |
| T | Clients switching the filter off | Bidding terms bounded: standards only within the relaxation range, budget only up, slots only down, If-Match, audited (`app/services/bidding_terms.py`, D54) | — |
| D | Search abuse (regex/NUL/huge queries) | `plainto_tsquery`, control characters stripped, ≤ 20 skill filters, whitelisted sort, validated keyset cursors, bounded `q` and `limit` (`app/services/marketplace.py`, D52) | — |
| D | Expensive bids view | Batched reads: 200 bids in ≤ 25 queries, < 2 s (`tests/perf/test_bids_view_perf.py`) | — |
| E | Double booking of developers | Availability reservations checked at bidding (`app/algorithms/availability.py`) | Must be re-checked when invitations are accepted (Phase 8) |

### Background jobs, email and Redis

| | Threat | Mitigation as implemented | Residual risk |
|---|---|---|---|
| E | Forged or stale job payloads | Jobs reload data and re-check state; never trust the payload (`app/jobs/tasks.py`); queue names allowlisted (`app/jobs/queues.py`) | — |
| T | Email header injection, HTML injection in emails | Header validation, HTML-escaped values, control characters stripped (`app/integrations/email.py`) | — |
| I | Lost or duplicated emails | Transactional outbox written in the business transaction, delivered with backoff (`app/services/outbox.py`, `app/jobs/email_jobs.py`) | Mailpit only in development/demos; production SMTP in Phase 15 |
| I/T | Redis access | Password required, only on the `app` network, no published port (`docker-compose.yml`) | Password visible on the Redis command line inside the container (accepted for development) |
| D | Redis down | Auth rate limits fail closed, other limits fail open and log; recommendation cache fails open | — |

### Frontend (SPA)

| | Threat | Mitigation as implemented | Residual risk |
|---|---|---|---|
| T | XSS | React escaping, no `dangerouslySetInnerHTML`/`eval` (ESLint + `scripts/check_forbidden.py`), strict CSP, Zod without eval (`frontend/src/features/auth/schemas.ts`) | — |
| I | Third-party tracking or supply-chain scripts at runtime | Everything self-hosted (fonts, 3D assets, stills); CSP `connect-src 'self'` | — |
| E | Trusting client-side guards | Guards only decide what to show; every check repeats on the server (`frontend/src/app/guards.tsx`) | — |
| I | Error reports leaking data | `/client-errors` size- and rate-limited, CSRF-protected, query strings and secrets removed (`app/services/client_errors.py`) | — |

### Supply chain, configuration and containers

| | Threat | Mitigation as implemented | Residual risk |
|---|---|---|---|
| T | Vulnerable or malicious dependencies | Hashed lock files, 14-day age rule except for security fixes (D1, D51), pip-audit, npm audit, Trivy, Semgrep, Bandit, gitleaks in the gate; Dependabot weekly | Node 20 end-of-life on laptops and in the Nginx build stage (move to Node 22 in Phase 6, D15) |
| I | Committed secrets | `.env` gitignored, `make env` generates secrets, gitleaks over the working tree, `.dockerignore` allowlist | — |
| E | Insecure production config | Startup refuses weak secrets, console SMS, debug, http origins, password-less Redis, `*` hosts, insecure cookies, CAPTCHA bypass (`app/core/config.py`) | — |
| E | Container escape / lateral movement | Non-root, read-only root FS, `no-new-privileges`, `cap_drop: ALL`, only Nginx publishes ports, `sandbox` network internal (`docker-compose*.yml`) | Judge0's isolation (Phase 13) depends on Judge0 |

### Later phases (to be filled in the phase that builds them)

| Component | Phase |
|---|---|
| Reputation engine inputs only from server-side evidence; settings validation | 6 |
| Formation runs (quotas, idempotency, timeouts, snapshot immutability, explanation visibility) | 7 |
| Invitations, lead permissions, team repair | 8 |
| Workspace, comments, SSE (cookie auth, Origin, connection limits), activity events | 9 |
| Ledger, escrow, `post_transaction()`, idempotency keys, money property tests | 10 |
| Reviews (blind visibility, immutability, integrity, trust weighting) | 11 |
| Disputes, admin console, step-up on sensitive actions, audit viewer, data export/deletion | 12 |
| GitHub token, webhooks, Judge0 isolation, SSRF and email header tests | 13 |
| ZAP baseline, load and chaos, final OWASP Top 10 checklist | 14 |
| Production configuration, backup encryption and restore drill | 15 |

## Controls implemented (Phase 0)
| Control | Where | Tests |
|---|---|---|
| Production config validation (weak secret, console SMS, debug, http origin, Redis without password, `*` hosts, insecure cookies, CAPTCHA bypass) | `backend/app/core/config.py` | `tests/unit/test_config.py` |
| Log redaction of secrets | `backend/app/core/logging.py` | `tests/unit/test_logging.py` |
| Safe errors (no traces, request id) | `app/core/errors.py`, `app/core/middleware.py` | `tests/unit/test_errors.py` |
| Trusted hosts, 256 KB body limit, security headers, route timeout | `app/main.py`, `app/core/middleware.py` | `tests/api/test_app.py` |
| Append-only, hash-chained audit log; least-privilege grants | `alembic/versions/0001_foundation.py` | `tests/integration/test_foundation_db.py` |
| DB roles: migrator / app / worker / readonly, no superuser, no BYPASSRLS | `infra/postgres/init/01-roles.sh` | `tests/integration/test_foundation_db.py::test_app_role_has_no_ddl` |
| TLS 1.2+, HTTPS redirect, HSTS, exact CSP, headers, TRACE blocked, body limits, timeouts, internal endpoints hidden | `infra/nginx/` | `tests/edge/test_edge.py`, `frontend/e2e/smoke.spec.ts` |
| Hardened containers (non-root, read-only, no-new-privileges, cap_drop ALL) | `docker-compose*.yml`, Dockerfiles | gate step 18 |
| Forbidden patterns, layer rules, gitleaks, Bandit, Semgrep, pip-audit, npm audit, Trivy | `backend/scripts/`, `infra/semgrep/` | gate steps 5–7 |
| Dependency update policy | `.github/dependabot.yml` | — |

## Controls implemented (Phase 1)
| Control | Where | Tests |
|---|---|---|
| Row-level security on every table (ENABLE + FORCE), fail-closed context, SECURITY DEFINER pre-auth functions | `alembic/versions/0002_identity_rls.py`, `app/db/context.py` | `tests/integration/test_rls.py`, `scripts/check_rls.py` |
| Argon2id passwords with rehash, zxcvbn ≥ 3, breached list, uniform timing | `app/core/security.py` | `tests/unit/test_security.py`, `tests/security/test_login_sessions.py` |
| Registration (uniform), phone OTP (hashed, 5 min, 5 attempts, 60 s resend), email links (hashed, single use) | `app/services/auth/registration.py` | `tests/security/test_registration_verification.py` |
| Opaque rotating sessions (15 min rotate + 30 s grace, 30/15 min idle, 7 days absolute), revoke/logout-all, Redis + DB | `app/core/sessions.py`, `app/core/auth_middleware.py` | `tests/security/test_login_sessions.py`, `tests/integration/test_sessions_ratelimit.py` |
| CSRF double-submit + Origin | `app/core/csrf.py` | `tests/unit/test_csrf_redirects.py`, `tests/security/test_login_sessions.py` |
| Rate limits (§14.8), progressive delay, lockout + email | `app/core/ratelimit.py`, `app/services/auth/login.py` | security + integration tests |
| ALTCHA CAPTCHA (single use), honeypot, minimum fill time, adaptive on login, always for admins | `app/core/captcha.py`, `frontend/src/lib/captcha.ts` | `tests/unit/test_captcha_email_totp.py`, security tests |
| Admin TOTP (AES-GCM secret, ±1 window, replay-proof), recovery codes, step-up | `app/services/auth/credentials.py`, `login.py` | `tests/security/test_admin_totp.py` |
| Admin area hidden (404) + separate frontend bundle | `app/core/authz.py`, `frontend/src/app/guards.tsx` | matrix test, `frontend/e2e/auth.spec.ts` |
| Central authorization + route × role matrix | `app/core/authz.py` | `tests/security/test_authz_matrix.py` |
| Open-redirect validator (server + client) | `app/core/redirects.py`, `frontend/src/lib/redirects.ts` | unit + property tests |
| Contract fuzzing (no 5xx, schema-conformant) | — | `tests/api/test_schemathesis.py` |
| Production: no test router, no docs | `app/main.py` | `tests/api/test_app.py` |

## Controls implemented (Phase 2)
| Control | Where | Tests |
|---|---|---|
| Strict CSP for every screen; per-response style nonce for runtime `<style>` (D23); no inline scripts/styles in the build; Zod without eval | `infra/nginx/*.conf`, `frontend/src/lib/nonce.ts`, `frontend/src/features/auth/schemas.ts` | `backend/tests/edge/test_edge.py` (exact CSP, nonce matches the page and changes per response), `frontend/e2e/csp.spec.ts` (all screens, dialogs and menus open), `frontend/tests/build/no-inline.test.ts` |
| Nothing loaded from other origins (fonts, 3D environment, stills all local) | `frontend/src/components/three/*`, `frontend/src/assets/stills` | `frontend/e2e/csp.spec.ts`, `frontend/e2e/home.spec.ts` |
| Dev-only tools (UI kit, stills renderer) never shipped | `frontend/src/app/router.tsx` (`DEV_TOOLS`) | gate step 2 + phase checks (`check_no_dev_tools`) |
| Fetch wrapper: CSRF, 401 → guards, 403/429 toasts with wait time, offline banner | `frontend/src/api/client.ts`, `frontend/src/app/queryClient.ts` | `frontend/src/api/client.test.ts`, `frontend/src/app/app.test.ts` |
| Route guards and role shells; admin navigation only in the admin chunk | `frontend/src/app/guards.tsx`, `RoleShell.tsx`, `features/admin/*` | `frontend/e2e/shell.spec.ts`, `auth.spec.ts` |
| Public stats expose aggregates only (definer function) | `alembic/versions/0003_public_stats.py` | `tests/integration/test_rls.py`, `tests/api/test_public.py` |
| Client error reports: size, rate limit, CSRF, sanitizing (no query strings or secrets in logs) | `app/api/v1/public.py`, `app/services/client_errors.py` | `tests/unit/test_client_errors.py`, `tests/api/test_public.py` |
| No dangerous DOM sinks; accessibility checks on every screen | ESLint, `scripts/check_forbidden.py` | gate steps 3, 6, 14 |

## Controls implemented (Phase 3)
| Control | Where | Tests |
|---|---|---|
| Upload pipeline: streamed to a 0600 temp file under a size limit; type by signature; polyglot, active-markup and PDF-action checks (hex-escaped names, compressed object streams); Pillow re-encode under a pixel budget (EXIF/GPS stripped, ≤ 4096 px); random UUID keys, sanitized names as metadata only (D31) | `app/uploads/*` | `tests/unit/test_uploads.py` (100% coverage), `tests/security/test_profiles_files.py`, `e2e/phase3.spec.ts` (GPS gone after download through Nginx) |
| Downloads: authorization in the `file_access` definer → 5-minute HMAC-signed URL → `X-Accel-Redirect` into an `internal` Nginx location with attachment, nosniff, sandbox CSP (D32) | `app/services/files.py`, `app/api/v1/files.py`, `infra/nginx/nginx.conf` | expiry, tamper, other key, IDOR tests; `e2e/phase3.spec.ts` headers |
| RLS on every new table (owner / admin; question bank admin + SYSTEM only); attempts and evidence written only by definers; taxonomy read-only; verification and stored-file identity guarded by triggers (D35); `caller_is_system()` in definers (D36) | `alembic/versions/0004_profiles_files_tests.py` | `tests/integration/test_rls_profiles.py` |
| Correct answers never leave the database: questions via `attempt_questions`, scoring via `score_test_attempt`; response schemas have no answer fields | `app/schemas/skill_tests.py`, migration 0004 | `tests/security/test_skill_tests.py` (schema assertion, lifecycle) |
| Server-side timer, late answers refused, one open attempt, 30-day retake rule, advisory lock against parallel starts (D33) | migration 0004, `app/services/skill_tests.py` | lifecycle tests, jobs tests |
| Mass assignment (`user_id`, `status`, `position`, `score`, `correct`) → 422; IDOR → 404; injection corpus stored as inert text; no email/phone on public profiles | `app/schemas/profiles.py`, services | `tests/security/test_profiles_files.py`, `test_authz_matrix.py` |
| Larger body limit only for POSTs to the upload routes; JSON stays 256 KB | `app/core/middleware.py` | `test_json_endpoints_keep_the_small_body_limit`, oversize test |

## Controls implemented (Phase 4)
| Control | Where | Tests |
|---|---|---|
| RLS on all 7 project tables (ENABLE + FORCE): drafts private to their client, non-DRAFT projects public, writes owner-only; child tables and the plan baseline follow project visibility via `project_visible()`/`is_project_client()` SECURITY DEFINER helpers (pinned `search_path`, EXECUTE revoked from PUBLIC) | `alembic/versions/0005_projects_planning.py` | `tests/integration/test_rls_projects.py` |
| Deny-by-default authz: `project.create/write/read/cancel`, `payment.verify`; ownership deferred to the service and returned as 404 (existence not leaked); admins can read/cancel but not edit others' drafts | `app/core/authz.py`, `app/services/projects.py` | `tests/security/test_authz_matrix.py`, `test_projects.py` (IDOR → 404) |
| Optimistic concurrency: `PATCH /projects/{id}` requires `If-Match`; stale write → 409 `VERSION_CONFLICT` (prevents lost updates / blind overwrite) | `app/api/v1/projects.py`, `app/services/projects.py` | `test_projects.py` version-conflict test |
| Publish guards in service **and** DB trigger: verified payment method (D39), ≥1 slot, shares = 100%, acyclic plan, schedule-risk ack (D40); baseline identity/content frozen by trigger | migration 0005, `app/services/projects.py` | `test_publish_requires_payment_then_succeeds`, `test_editing_after_publish_is_rejected` |
| Mass assignment (`client_id`, `status`, `version`) → 422; CPM cycle → 422 (not a hang); whole-set replaces validated (Σ shares, Σ counts); no raw SQL (ORM only) | `app/schemas/projects.py`, `app/algorithms/cpm.py` | `test_projects.py`, `tests/algorithms/test_cpm.py` |

## Controls implemented (Phase 5)
| Control | Where | Tests |
|---|---|---|
| Sealed bids in the database: RLS on `bids`/`availability_reservations` makes a bid visible only to its developer, the project's client and admins — never another developer; writes are the bidder's while BIDDING (or SYSTEM) | `alembic/versions/0006_marketplace_bidding.py` | `tests/integration/test_rls_bids.py`, `tests/security/test_bids.py` |
| Sealed-bid authorization: `bid.view` (client/admin only) for the all-bids view, `bid.read` (developer) for `/me/bids`; a developer gets 404/403, never another's bid; marketplace responses never select bid columns | `app/core/authz.py`, `app/services/marketplace.py` | `test_authz_matrix.py`, `test_bids.py` |
| Eligibility computed in a SYSTEM session with minimal additive RLS (D50); the caller is authorised as the project owner first and only the verdict is returned | migration 0006, `app/services/bids.py` | `test_bids.py::test_client_sees_all_bids_with_eligibility` |
| Search input safety: `plainto_tsquery` (no user regex), whitelisted filters/sort → 422, tampered cursor → 422 | `app/services/marketplace.py` | search tests |
| Bid rules: one ACTIVE bid per project (partial unique), bid only while BIDDING (409), rate limit 20/h; mass assignment (`status`, `developer_id`, `ineligible_reasons`) → 422 | `app/services/bids.py`, `app/schemas/bids.py` | `test_bids.py` |
| Reputation snapshots public-read, SYSTEM-write; the "seeded" marker shows only outside production | migration 0006, `app/services/reputation_read.py` | `test_rls_bids.py` |

## Dependency update policy (§14.21)
Dependabot weekly (pip, npm, Docker, GitHub Actions). Critical vulnerabilities fixed within
48 hours, high within 7 days. `make lock` re-resolves Python locks; the gate fails on unfixed
high/critical findings.

## Residual risks (§14.14)
Simulated payments only; determined collusion with many real identities can evade rules;
self-hosted TLS certificates in development; Judge0 sandbox strength depends on Judge0;
SMS simulated in development; no third-party penetration test.
