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

## Phase 5 endpoints — marketplace, sealed bids (spec §10 Marketplace/Bids, §9.2)

Marketplace is developer-only and read-only; it never returns any bid data (sealed, §14.5).

- `GET /projects/search?q=&skills=&budget_min=&budget_max=&deadline_max=&team_size=&sort=&cursor=&limit=`
  → cursor page of project cards. Full-text (`plainto_tsquery`) over title+summary; whitelisted
  filters (unknown params → 422); `sort ∈ {newest, budget, deadline}`. `GET /projects/recommended`
  → projects matching the developer's skills (§9.16). (Developer.)
- `GET /public/projects` · `GET /public/projects/{id}` → the public marketplace: open projects with
  limited columns and, for one project, its slots; never any bid data. (Anyone.)
- `POST /projects/{id}/bids` → place a sealed bid (one standing bid per project; only while
  BIDDING, else 409 `INVALID_STATE`; at most 30 open bids per developer, else 409
  `LIMIT_REACHED`, §14.8). `GET /me/bids?project_id=&status=&cursor=&limit=` → cursor page of my
  bids, newest first. `GET /bids/{id}` → one of my bids with its project, the actions still open
  and, while bidding is open, how it stands against the project's requirements.
  `PATCH /bids/{id}` · `DELETE /bids/{id}` (withdraw), both with `If-Match: <version>` (stale →
  409 `VERSION_CONFLICT`). All developer-owned; another developer's bid is 404. (Developer.)
- `POST /projects/{id}/bids/eligibility` → dry-run Algorithm 1 for the bid sheet's live preview
  (per-constraint pass/fail + reason; not persisted, D45). (Developer.)
- `GET /projects/{id}/bids` → all bids on the caller's own project with reputation (C, P) and the
  eligibility verdict + reasons, slot coverage, relaxations and the too-few flag. (Client, own;
  admin.)

## Phase 6 endpoints — reputation (spec §10.2 Reputation, D101)

- `GET /developers/{id}/reputation` → the six parameters (`omega`, `x`, `xm`, `beta`, `mu`, `t`),
  `competency`, `performance` (0–1, 3-place decimal strings), `completed_projects`,
  `distinct_clients`, `is_newcomer`, `seeded`, `simulated`, per-skill competency and — for the
  developer themself while a newcomer — `newcomer` (verified items, evidence domains, the default
  quality, the threshold). Follows the profile's visibility: hidden, unknown or non-developer ids
  are 404. (Any active signed-in user.)
- `GET /me/reputation/history?cursor=&limit=` → my completed projects, newest first, each with
  its changes (`parameter`, `old`, `new`, `raw_new`, `capped`, `reason` — one plain sentence).
  Cursor page (§10.1), `limit` 1–100. (Developer, own.)
- No endpoint writes reputation: it is computed by the `reputation.recalculate_all` job from the
  stored histories (`make reputation-recalculate`; the admin endpoint arrives in Phase 12, D92).

## Phase 7 endpoints — team formation and jobs (spec §10.2 Formation, §10.3; D106–D110)

- `POST /projects/{id}/formation-runs` (client, own FORMING project; `Idempotency-Key`; quota
  `ratelimit.formation_run` 10/h; one run at a time per project) — body `preset`
  (`balanced|quality|fast|budget`), optional `weights` {competency, teamwork, time, cost} 0–1
  (normalised; all zero is 422), `min_newcomers` 0–2, optional `min_performance` /
  `min_competency` (≥ the D54 floor). Any other field (`seed`, `status`, `result`, …) is 422.
  → 202 `{run_id, job_id, status, progress}`. 409 `INVALID_STATE` when not FORMING or no eligible
  bids, 409 `LIMIT_REACHED` while a run is in progress, 503 when the queue is down.
- `GET /projects/{id}/formation-runs` (client own, admin) → the runs, newest first, up to 50
  (`id, status, preset, min_newcomers, fitness, optimal, price_paisa, confirmed, …`).
- `GET /formation-runs/{id}` (client own, admin) → params, seed, `result` (team with each
  member's contribution, fitness, price/budget and finish/deadline shares, risks, deciding term
  and runner-up difference, exact verification, fairness with the cost of fairness, top three
  teams, convergence, relaxations), `can_confirm`, `confirmed`.
- `POST /formation-runs/{id}/confirm` (client own) → `{team_id, project_status: TEAM_PENDING,
  members, invitations_sent: false}`; 409 when the project isn't FORMING, the run has no team, or
  a chosen bidder withdrew.
- `POST /formation-runs/{id}/verify` (admin, step-up; others 404) → 202; re-runs the frozen
  inputs and records `admin_verification.reproduced` on the run.
- `GET /admin/formation-runs?cursor=&limit=` (admin) → cursor page of every run.
- `GET /bids/{id}/explanation` (the bidder; admin) → why the bid was not selected: `reasons`,
  `main_gap` (`comp|team|time|cost`), `hint`, `gap`, `price_counterfactual_paisa`, and `compare`
  (the selected bid's days and price in that slot — never who). 404 until a team was confirmed
  without the bid (or for anyone else's bid).
- `GET /jobs/{id}` (requester, admin) → `{id, type, status, progress, error_code, created_at,
  started_at, finished_at}`; others' jobs and system jobs 404.
- `GET /jobs/{id}/events` (requester, admin) → `text/event-stream`: a `status` event, then
  `progress` events with `id` (resume with `Last-Event-ID`), a heartbeat comment every 20 s, the
  end on a final status or after 30 min. 403 `CSRF_FAILED` for a foreign `Origin` or a
  cross-site `Sec-Fetch-Site`, 429 for a fourth open stream.

Error envelope: `{"error": {"code", "message", "fields"?, "request_id"}}`.
