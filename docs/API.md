# API

The contract is `docs/api/openapi.json` (generated from code; the gate fails on drift).
Regenerate with `make openapi`. Conventions: spec §10.1; contract rules: §10.4.

## Phase 0 endpoints
| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/api/v1/health` | Liveness | Public |
| GET | `/api/v1/health/ready` | DB, Redis, queue readiness | Internal network only (Nginx returns 404) |
| GET | `/metrics` | Prometheus metrics | Internal network only |

## Phase 1 endpoints
Accounts and authentication (spec §10.2 Auth, Me): `GET /captcha/challenge`, `GET /auth/csrf`,
`POST /auth/register`, `/auth/login`, `/auth/login/totp`, `/auth/logout`, `/auth/logout-all`,
`GET /auth/sessions`, `DELETE /auth/sessions/{id}`, `POST /auth/otp/send|verify`,
`/auth/email/verify|resend`, `/auth/password/forgot|reset|change`, `/auth/totp/setup|confirm`,
`/auth/recovery-codes/regenerate`, `/auth/step-up`, `GET|PATCH /me`, `GET /admin/session`.
Every state-changing request needs `X-CSRF-Token` (from `GET /auth/csrf`) and a same-origin
`Origin`. Public forms carry `captcha`, `website` (honeypot) and `started_at_ms`.

## Phase 2 endpoints
- `GET /public/stats` (public, cached 5 min, `Cache-Control: public, max-age=300`): live
  homepage numbers; a field is present only when it exists and is non-zero
  (`{"developers": 42}`). Aggregates come from the SECURITY DEFINER function `public_stats()`.
- `POST /client-errors` (public, CSRF + Origin, ≤ 8 KB, 10/min + 50/h per IP): frontend error
  summary `{message, stack?, path, kind: render|chunk|unhandled, request_id?}` → 204. Sanitized
  (control characters, query strings, secret-like strings) and logged; nothing is stored.

Error envelope: `{"error": {"code", "message", "fields"?, "request_id"}}`.
