# Security

Written from spec §14; grows every phase (§14.13). Each control links to its tests.

## Threat model (STRIDE summary)
See spec §14.2. Full table to be completed in Phase 14.

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

## Dependency update policy (§14.21)
Dependabot weekly (pip, npm, Docker, GitHub Actions). Critical vulnerabilities fixed within
48 hours, high within 7 days. `make lock` re-resolves Python locks; the gate fails on unfixed
high/critical findings.

## Residual risks (§14.14)
Simulated payments only; determined collusion with many real identities can evade rules;
self-hosted TLS certificates in development; Judge0 sandbox strength depends on Judge0;
SMS simulated in development; no third-party penetration test.
