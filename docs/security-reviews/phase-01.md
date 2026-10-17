# Security review — Phase 1 (Accounts, authentication, sessions, security core)

- **Date:** 2026-10-17
- **Reviewer:** Claude Code (`/security-review` on `origin/main...phase-1`, 136 files), with
  Mashfikuzzaman Taeen. The analysis was done in the main session (the author has full
  context of the code) instead of separate sub-agents.
- **Scope:** migration 0002 (RLS + SECURITY DEFINER functions), `app/core/*` (security,
  sessions, CSRF, rate limits, authz, CAPTCHA, redirects, idempotency, middleware),
  auth services and routers, integrations (email, SMS), jobs, test-only router, frontend
  auth screens, fetch wrapper and guards.
- **Tester's human check (spec §14.22):** _pending (Sara Binte Shafayet)_

Unresolved high findings: 0

## Result of the `/security-review` pass

No high-confidence (≥ 8/10) vulnerabilities were found. Areas specifically checked:

| Area | Conclusion |
|---|---|
| SQL injection | All queries are SQLAlchemy expressions; SECURITY DEFINER functions take typed parameters; no string-built SQL in `app/`. |
| Authentication bypass | Sessions are opaque 256-bit tokens looked up by SHA-256; admins get no session from the password alone (pre-auth token + TOTP/recovery code); TOTP replay blocked by `last_used_step`. |
| Authorization | Deny-by-default `authorize()`; route × role matrix test covers every OpenAPI operation; admin/TOTP routes answer 404 to everyone else (including anonymous). |
| Row-level security | ENABLE + FORCE on all 13 tables; `is_system()` requires the worker DB role, so web requests cannot claim SYSTEM; definer functions return only the columns each pre-auth flow needs; `auth_create_user` refuses ADMIN. Cross-user read/write tests per table. |
| CSRF | Session-bound double-submit token + exact Origin/Referer check on every state-changing operation; anonymous tokens are invalid for sessions. |
| Session management | Fixation impossible (new token on login), rotation with 30 s grace, idle/absolute expiry, logout(-all), revocation in Redis and DB, cookie flags `__Host-`/HttpOnly/Secure/SameSite. |
| Secrets & crypto | Argon2id (m=64 MiB, t=3, p=2) with rehash; OTPs HMAC-hashed with a derived key; TOTP secrets AES-256-GCM with the user id as associated data; tokens from `secrets`; constant-time comparisons. |
| Open redirect | `return_to` validated server- and client-side (relative path, no `//`, `\`, scheme or control characters, known route shapes). React Router 7.18 used (6.x open-redirect advisory, D20). |
| XSS / injection in emails | Email templates escape every value for HTML, strip control characters, reject header injection; React renders text only. |
| Data exposure | Uniform answers for register/forgot/login; `MeResponse` has no hashes or secrets; logs redact secrets; outbox links scrubbed after sending; test-only router mounted only when `DEVSYNC_ENV=test` (tested). |

## Findings fixed during the phase (found by tests, fuzzing and this review)

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Medium | A session cached the account status from sign-in, so a newly verified account stayed "PENDING" in its current session — and, once suspension exists (Phase 12), a suspended user's cached "ACTIVE" would outlive the suspension. | **Fixed:** `SessionStore.refresh_status()` updates every live session when the status changes (used on activation; Phase 12 suspension must call it too). Test added. |
| 2 | Medium | Two rate-limit rules with the same window length shared one Redis counter, making the stricter rule fire on the first request. | **Fixed:** one counter per rule (`rl:{scope}:{window}s:{limit}:{key}`); test added. |
| 3 | Low | Admin-only TOTP routes answered 401 to anonymous callers, confirming they exist. | **Fixed:** `HIDDEN_ACTIONS` answer 404; matrix test. |
| 4 | Low | CSRF check ran before method routing, so unsupported methods (TRACE/PUT on POST-only routes) got 403 instead of 405 (found by schemathesis). | **Fixed:** CSRF applies only to existing state-changing operations. |
| 5 | Low | A malformed client address (`testclient`, or junk from a misconfigured proxy) caused a 500 when stored in `inet` columns. | **Fixed:** `valid_ip()` before storing. |
| 6 | Low | `INSERT … RETURNING` on append-only/write-only tables required read access under RLS. | **Fixed:** `implicit_returning=False` on `audit_log` and `email_outbox`. |
| 7 | Info | `npm audit`: React Router 6 open-redirect advisory. | **Fixed:** React Router 7.18.4 (D20). |

## Accepted / carried forward

- Account lockout after 10 failures can be triggered by someone who knows a user's email
  (inherent to the spec's lockout control; mitigated by CAPTCHA, progressive delays and a
  15-minute lock; DoS-class, out of scope for this review).
- Phase 0 low findings 4–5 (Redis password on the command line, dev TLS key mode 644) remain
  accepted for development.
