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

Error envelope: `{"error": {"code", "message", "fields"?, "request_id"}}`.
