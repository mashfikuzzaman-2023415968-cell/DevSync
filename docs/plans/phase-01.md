# Phase 1 — Accounts, authentication, sessions, security core (plan)

## Context
Phase 0 is done (gate PASS, tag `phase-0`, pushed). Phase 1 (spec §17 "Phase 1") builds the hardened identity layer and the security framework every later phase relies on: registration with phone OTP + email verification, login with lockout and adaptive CAPTCHA, server-side rotating sessions, CSRF, rate limiting, admin TOTP + recovery codes + step-up, the central authorization module with the route × role matrix harness, **row-level security** in Postgres, the redirect validator, and the frontend auth screens (functional; restyled in Phase 2). Outcome: `make gate PHASE=1` → `PHASE 1 GATE: PASS`, security suite non-empty, no route without an authz-matrix entry; commit `phase-1: …`, tag, push (as for Phase 0).

Read: §2, §7.1, §8 (User), §10 (Auth, Me), §12, §14.4–14.8, §14.10, §14.13 row 1, §14.15–14.18, §16.4. Skills: `frontend-design` for the auth screens (devsync-ui arrives in Phase 2).

## Dependencies to add (recorded as DECISIONS D19)
Backend (spec-named): `argon2-cffi`, `pyotp`, `zxcvbn`, `altcha`. Not named but required: `cryptography` (AES-GCM + HKDF for TOTP secrets, §14.4), `email-validator` (pydantic `EmailStr`). Frontend (spec-named): `react-router-dom@6` (latest 6.x), `@tanstack/react-query@5`, `react-hook-form`, `zod`, `@hookform/resolvers`, `openapi-typescript` (dev). Breached-password list: top-100k common passwords (SecLists, MIT) stored as gzipped SHA-1 hex in `backend/app/core/data/breached-100k.sha1.gz` (offline, §3).
CAPTCHA widget: a small in-house ALTCHA-protocol solver component (SHA-256 proof of work via `crypto.subtle`, keyboard accessible) instead of the npm widget, whose runtime-injected styles/blob workers conflict with the strict CSP (§14.3). Server side uses the spec's `altcha` library.

## Database — migration `0002_identity_rls`
- Tables (§7.1): `users` (citext email, E.164 phone unique nullable, role/status enums, lockout fields), `sessions` (token_hash, csrf_secret, ip, ua, last_seen, expires_at, revoked_at, step_up_until, totp_verified), `otp_codes`, `email_tokens`, `totp_credentials` (AES-GCM secret, `last_used_step`), `recovery_codes` (Argon2id), `devices_seen`, `notifications` (table only), `email_outbox`; FK from `audit_log.actor_id`/`jobs.requested_by`/`idempotency_keys.user_id` to `users`; indexes from §7.9 (`sessions(user_id, revoked_at)`, `notifications(user_id, read_at, created_at DESC)`).
- **RLS foundation (§14.15):** helper SQL functions `app_uid()`, `app_role()`, `is_admin()` (STABLE, pinned `search_path`; project helpers come with their tables later); `ENABLE` + `FORCE ROW LEVEL SECURITY` and policies on every table so far: own-row policies for identity tables, `notifications` own rows, `email_outbox` insert-any/read+update SYSTEM, `audit_log`/`platform_settings` admin read + SYSTEM, `jobs`/`idempotency_keys` own rows. Fail closed when `app.user_id` is unset. A `TO devsync_migrator USING (true)` policy keeps migrations and owner-run checks working.
- **Pre-auth lookups** (login by email, session restore by token hash, consuming email/OTP tokens) go through narrow `SECURITY DEFINER` functions owned by the migrator that return only the needed columns, so web requests never need a SYSTEM context.
- Request context: the DB session dependency runs `set_config('app.user_id'/'app.role', …, true)` per transaction; workers connect as `devsync_worker` with `app.role='SYSTEM'`.
- Settings v2: adds the `ratelimit.*` group (§14.8 table) via a new frozen seed snapshot; the v1 test becomes "v1 validates; v2 equals current defaults".

## Backend — core modules (`backend/app/core/`)
- `security.py`: Argon2id (t=3, m=64 MiB, p=2) with rehash-on-login; dummy-hash on unknown users (timing); password policy (10–128 chars, zxcvbn ≥ 3, breached-list check); `secrets` token generation; HMAC-SHA256 helpers; `hmac.compare_digest`; AES-GCM encrypt/decrypt with key = HKDF(SECRET_KEY, info="totp").
- `sessions.py`: 256-bit opaque token in `__Host-ds_session` (HttpOnly, Secure, SameSite=Lax, Path=/); SHA-256 stored; Redis record + DB row; rotation every 15 min with 30 s grace for the old token; idle 30 min (admin 15), absolute 7 days; rotate on login/privilege change/step-up; list/revoke/revoke-all; Redis miss → restore from DB row.
- `csrf.py`: double-submit `__Host-ds_csrf` (readable, Secure, SameSite=Strict) = nonce + HMAC(session csrf_secret, nonce); anonymous forms use a SECRET_KEY-derived key; all unsafe methods need matching `X-CSRF-Token` **and** `Origin`/`Referer` = `PUBLIC_ORIGIN`.
- `ratelimit.py`: Redis sliding-window Lua script; `limit(scope, key_fn)` route dependency reading `ratelimit.*` settings (in-process cache, 60 s); 429 + `Retry-After`, security-event log, alert counter; fails **closed** for auth endpoints and **open** for reads when Redis is down (§16.8).
- `authz.py`: deny-by-default policy registry `authorize(user, action, resource)`; roles CLIENT/DEVELOPER/ADMIN (+ GUEST); 401/403/404 semantics; ownership hooks used later.
- `redirects.py`: `return_to`/`link_path` validator (relative, single leading `/`, no `//`, `\`, scheme or control chars, must match a known route pattern) → else role home.
- `idempotency.py`: Idempotency-Key storage/replay (used from Phase 5/10; implemented and tested now).
- `captcha.py`: ALTCHA challenge (HMAC `CAPTCHA_HMAC_KEY`, 5 min) + single-use verification (Redis); honeypot field + minimum fill time 2 s; bypass only when `DEVSYNC_ENV=test` (startup fails otherwise).
- Middleware chain completed (§14.10): session load → CSRF → rate limit slots filled.

## Backend — services, endpoints, jobs
Services in `app/services/auth/` (register, verification, login, sessions, password, totp, me), repositories in `app/repositories/users.py` etc., integrations `app/integrations/sms.py` (`console` dev, `noop` test, startup refuses console in prod) and `email.py` (SMTP via transactional outbox; stdlib templates with HTML escaping, plain + HTML; header-injection safe), job `email.send` (every 30 s, 5 retries with backoff) and `lifecycle.expire` (sessions/tokens cleanup).

Endpoint contract (all requests `extra="forbid"`; errors in the §10.4 envelope; every op declares 401/403/404/422/429 as applicable with examples):

| Op | Request | Success | Main errors |
|---|---|---|---|
| GET `/captcha/challenge` | — | 200 challenge | 429 |
| GET `/auth/csrf` | — | 204 + cookie | — |
| POST `/auth/register` | name, email, phone, password, role (CLIENT/DEVELOPER), terms, captcha, honeypot | **202 uniform** ("check your email and phone"); new account PENDING, email token + OTP sent; duplicates get the same response and a notice email to the existing owner | 422 (policy/breached), 429, 403 CSRF/captcha |
| POST `/auth/login` | email, password, captcha? | 200 `{redirect_to}` + session; admins → 200 `{totp_required, pre_auth}` (no session) | 401 uniform, 423 locked (with time), 429 |
| POST `/auth/login/totp` | pre_auth token, code or recovery code | 200 session | 401, 429 |
| POST `/auth/otp/send`, `/auth/otp/verify` | — / code | 204 | 409 already verified, 422, 429 |
| POST `/auth/email/verify` (public), `/auth/email/resend` | token / captcha | 204 | 400 invalid/expired, 429 |
| POST `/auth/logout`, `/auth/logout-all` | — | 204 | 401 |
| GET `/auth/sessions`, DELETE `/auth/sessions/{id}` | — | list / 204 | 401, 404 |
| POST `/auth/password/forgot` (uniform), `/reset`, `/change` | email+captcha / token+password / current+new | 202 / 204 (all sessions revoked) / 204 | 400, 401, 422, 429 |
| POST `/auth/totp/setup`, `/totp/confirm`, `/recovery-codes/regenerate`, `/auth/step-up` | — / code / step-up code / code | provisioning URI / 10 codes once / 204 (10 min) | 401, 403/404 non-admin, 422 |
| GET/PATCH `/me` | display_name | user (role-specific schema) | 401, 422 |
| GET `/admin/session` | — | admin security summary (proves admin hiding) | **404 for everyone else** |
| `/__test__/seed` (test env only) | role, verified flags | users + OTP peek | absent elsewhere (startup assertion) |

Lockout: progressive 429 with growing `Retry-After` after 5 failures; 10 failures/hour → locked 15 min + email notice; CAPTCHA required after 3 failures (account or IP) and always for admin login. New-device login → email (`devices_seen`). Audit entries for every auth/security event and admin action. `scripts/create_admin.py` (interactive; prints the TOTP provisioning URI once; `make create-admin`).

## Frontend (screens 2–5, functional)
React Router 6 data router with lazy routes; TanStack Query; `src/api/` typed client generated from `docs/api/openapi.json` (`openapi-typescript`) + fetch wrapper (credentials same-origin, CSRF header, 401 → `/login?return_to=…`, 403 toast, 429 retry time, offline banner, 15 s abort); `lib/redirects.ts` mirrors the server validator. Screens: Login, Admin TOTP (6-box input + recovery code), Register (role cards → details with strength meter → verify), Verify (OTP boxes with paste + 60 s resend countdown, email status), Forgot/Reset, placeholder role homes `/client`, `/dev`, `/admin` (admin chunk lazily loaded only after `/me` confirms an admin with TOTP), `/403`, `/404`. Route guards: unauthenticated, wrong role, PENDING → `/verify`, admin without TOTP → `/admin/setup-2fa`. RHF + Zod schemas mirroring backend limits. In-house CAPTCHA solver component.

## Security (§14.13 row 1 — all)
RLS foundation + `check_rls.py` enforced; ALTCHA + honeypots; admin hidden (404 + separate bundle); production debug-off checks; Argon2id; registration/OTP/email/login/reset flows; sessions + rotation + timeouts; CSRF; rate limits + auth limits; lockout; uniform errors; hash-chained audit; admin TOTP + recovery + step-up; authz module + matrix harness; redirect validator; log redaction (existing).

## Tests
- unit: every core module (≥ 95% coverage for security, sessions, csrf, authz, ratelimit, redirects); password policy, Argon2 rehash, AES-GCM round trip/tamper, TOTP window ±1 + replay, recovery codes single-use.
- property: token uniqueness; redirect validator over hypothesis-generated paths (never off-site).
- integration/RLS: for every protected table, cross-user reads/writes via repositories as `devsync_app` return nothing/fail; GUEST sees nothing private; SECURITY DEFINER functions expose only intended columns.
- api + security (§16.4): authz matrix over every OpenAPI route × {anonymous, client, other client, developer, other developer, admin} (fails on a missing entry); IDOR (sessions of others → 404); mass assignment (`role`, `status`, `email_verified_at` → 422); CSRF (missing/wrong token, foreign Origin → 403; GET never mutates — DB checksum); session fixation, idle/absolute expiry, rotation + grace, logout(-all), cookie flags; uniform errors + timing (< 50 ms diff over 50 samples); lockout/unlock; OTP expiry/attempts/resend; reset token single-use/expiry; breached passwords; TOTP replay/window; step-up enforcement; every §14.8 auth limit → 429 + `Retry-After` + reset; CAPTCHA missing/expired/replayed/tampered + adaptive + honeypot; admin hiding 404; production mode refuses debug/test router; redirect attacks; malicious client (forged role/ids).
- fuzz: schemathesis on all operations (200 examples each): zero 500s, schema-conformant.
- jobs: email outbox send/retry/backoff idempotency; expiry cleanup.
- frontend: components, schemas, guards, fetch wrapper, redirect validator, CAPTCHA solver (unit, MSW).
- E2E (Chromium): register → OTP (from test seed) → email link (Mailpit API) → role home; wrong password ×N → lockout message; admin login with TOTP; logout-all invalidates another browser context; admin JS never requested by non-admins.

## Gate (P1 additions)
Step 6 enforces `check_rls.py`; step 10 security suite non-empty; step 11 schemathesis; `PHASE_CHECKS[1]`: scripted register + verify + login via API, admin TOTP flow, observed 429 on login, audit chain verifies. Coverage: backend 75% / frontend 60%, security modules ≥ 95%.

## Housekeeping
Save this plan as `docs/plans/phase-01.md`; record D19 (new deps, in-house CAPTCHA widget, SECURITY DEFINER pre-auth functions, migrator RLS policy) in DECISIONS.md; regenerate `docs/api/openapi.json`; update SECURITY.md / TESTING.md / API.md; `/security-review` (now runnable against `origin/main`) → `docs/security-reviews/phase-01.md`; PROGRESS.md; commit `phase-1: …`, tag `phase-1`, push `main` + tag (token passed per command, not stored).

## Verification
`make gate PHASE=1` prints `PHASE 1 GATE: PASS`. Manual: register a client and a developer, read the OTP from the dev log and the email link in Mailpit (`http://127.0.0.1:8025`), log in/out, see the sessions list, confirm admin login demands TOTP (`make create-admin`).

## Risks
Scope is large (biggest security phase); RLS + SECURITY DEFINER design is the trickiest part and is tested table by table. Existing dev databases need `make migrate` only (no new DB roles required).
