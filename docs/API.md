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

## Phase 3 endpoints
Profiles and evidence (Developer unless noted; every request body rejects unknown fields):
- `GET/PATCH /me/developer-profile` — headline ≤ 120, bio ≤ 2000, hours 1–80, GitHub username,
  IANA time zone, visibility `PUBLIC|CLIENTS_ONLY`; PATCH sends only changed fields (autosave).
- `PUT /me/skills` — replace the list: ≤ 20 `{skill_id, self_level 1–5}`, each skill once.
- `GET/POST /me/portfolio`, `PATCH/DELETE /me/portfolio/{id}`, `PUT /me/portfolio-order`
  (every id once) — ≤ 20 items, https links, ≤ 8 skills.
- `POST /me/portfolio/{id}/images` (multipart `file`, ≤ 5 per item),
  `DELETE /me/portfolio/{id}/images/{image_id}`.
- `GET/POST /me/certificates` (multipart `title`, `issuer`, `file`), `PATCH` (pending only),
  `DELETE /me/certificates/{id}` — status stays `PENDING` until an admin decides.
- `GET/POST /me/external-reviews` (multipart `source`, `rating`, `scale`, `project_date`,
  `file`; `rating_norm = rating / scale`), `DELETE /me/external-reviews/{id}`.
- `GET/PATCH /me/client-profile` (Client) — organisation, description, https website.
- `GET /skills` (any verified account) — the taxonomy.
- `GET /developers/{id}` (session) and `GET /public/developers/{id}` (public, rate limited) —
  visibility-filtered profile: skills, verified scores, portfolio with image ids, verified
  certificates; never email or phone. Hidden and missing look the same (404).

Files (D31, D32):
- `GET /files/{id}/download` (public; authorized in the `file_access` definer) → 302 to
  `/files/blob/{key}?t&n&e&s`, a 5-minute HMAC-signed link; the blob endpoint answers with
  `X-Accel-Redirect` and Nginx streams the bytes (attachment, nosniff, sandbox CSP).
  Uploads: 422 with `fields.file` for a refused file, 413 when too large, 429 after 20/hour.

Skill tests (Developer, D33):
- `GET /skill-tests` — each test with `last_score`, `next_attempt_at`, `open_attempt_id`.
- `POST /skill-tests/{id}/attempts` (10/hour) → 201 attempt: questions (text + 4 options, no
  answers), `deadline_at`, `server_now`; 409 `IN_PROGRESS` (with `attempt_id`) or
  `RETAKE_LOCKED` (with `next_attempt_at`).
- `GET /attempts/{id}` — scores an expired attempt as it stands.
- `POST /attempts/{id}/answer` `{question_id, choice 0–3}` → `{answered}`; 409 `EXPIRED`/
  `SUBMITTED` after the deadline or submit.
- `POST /attempts/{id}/submit` → `{score, correct, total, added_to_profile}`; 409 if submitted.

## Phase 4 endpoints — projects and the CPM planner (spec §10.2)

Clients own projects; drafts are private until published for bidding. All writes are CLIENT-only
and object-scoped (a foreign project → 404); reads are the owning client or an admin.

- `GET /projects` → the caller's projects (`ProjectListItem[]`). `POST /projects` → create a DRAFT
  (`ProjectCreate` → `ProjectOut`).
- `GET /projects/{id}` → `ProjectOut`. `PATCH /projects/{id}` → edit a DRAFT; requires an
  `If-Match: <version>` header (optimistic concurrency; stale → 409 `VERSION_CONFLICT`).
  `DELETE /projects/{id}` → delete a DRAFT.
- `PUT /projects/{id}/slots` → whole-set replace of skill slots (Σ count = team size, 2–10).
  `PUT /projects/{id}/milestones` → whole-set replace (Σ `share_bp` = 10000). `PUT
  /projects/{id}/dependencies` → whole-set replace of finish-to-start edges (acyclic; a cycle →
  422 with the cycle listed).
- `POST /projects/{id}/plan/preview` → run CPM on an unsaved plan (`PlanPreviewIn` →
  `CpmPreviewOut`: schedule, duration, all critical paths, warnings; no persistence). `GET
  /projects/{id}/plan` → the current/baseline schedule (`PlanOut`).
- `POST /projects/{id}/publish` → DRAFT → BIDDING after the §8 guards (verified payment method,
  ≥1 slot, shares = 100%, acyclic; `acknowledge_schedule_risk` required when CPM > deadline, D40);
  writes plan baseline v1. `POST /projects/{id}/extend-bidding` → extend the bidding deadline
  (capped). `POST /projects/{id}/cancel` → cancel with a reason (owner or admin).
- `POST /me/payment-method/verify` → mark the client's simulated payment method verified (D39;
  CLIENT-only, idempotent).

Error envelope: `{"error": {"code", "message", "fields"?, "request_id"}}`.
