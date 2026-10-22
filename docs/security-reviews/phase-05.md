# Security review — Phase 5 (Marketplace, sealed bidding, Algorithm 1 filtering)

- **Date:** 2026-10-20
- **Reviewer:** Claude Code (`/security-review` method on `main...phase-5`), with Salwa Baki. A
  manual review read the security-critical surfaces (migration `0006` RLS, the sealed-bid authz
  policies and matrix, the bids/marketplace services, the eligibility SYSTEM-session path, the
  search query builder, and the bidding-deadline job) against the Phase 1–4 patterns; findings
  filtered at confidence ≥ 8/10.
- **Scope:** `bids`, `availability_reservations`, `reputation_snapshots` and the project
  `search_vector` (migration 0006, RLS + SYSTEM policies); `algorithms/filtering.py`; the
  marketplace search/recommended and bids CRUD/eligibility/client-view services and routes; the
  `bid.*`/`marketplace.read`/`reputation.read` authorization policies; and the `bidding.deadline`
  job.
- **Tester's human check (spec §14.22):** _pending_ (log in as two developers and the client in
  three browser profiles and confirm bid secrecy, spec §17 Phase 5 manual check).

Unresolved high findings: 0

## Result of the review

No high-confidence (≥ 8/10) vulnerabilities were found. The headline risk — **sealed bids** — is
defended in depth and tested from three angles.

| Area | Conclusion |
|---|---|
| Sealed bids (the core requirement) | Defended at three layers: (1) authorization — `/me/bids` is developer-only and the all-bids view is client/admin-only, so a developer never reaches another's bid (→ 404/403); (2) **RLS** — `bids` and `availability_reservations` are ENABLE+FORCE with a SELECT policy of bidder-or-project-client-or-admin, proven directly as `devsync_app` (`test_rls_bids.py`: a second developer and a guest see zero rows, and cannot write another's bid); (3) marketplace responses never select bid columns, and search/recommended return only project cards. A cross-context E2E check is written for Demo-1 readiness. |
| SYSTEM eligibility widening (D50) | Algorithm 1 reads bidders' skills/evidence/reputation, which the client can't read directly, so the client-bids view and the deadline job evaluate in a SYSTEM session. The added policies are **SELECT-only for the worker role under `app_role()='SYSTEM'`** (plus skill-evidence INSERT and a projects status UPDATE for jobs); a web request can never set the SYSTEM context (RLS §14.15, tested: the web role cannot write a reputation snapshot). The client is authorised as the project owner before the SYSTEM read, and only the eligibility verdict — never raw developer rows — is returned. |
| Search injection | The free-text query goes through PostgreSQL `plainto_tsquery` (no user-supplied tsquery or regex); filters and `sort` are whitelisted (unknown → 422); the keyset cursor is base64 of `created_at|id` and a tampered/garbage cursor is a typed 422, not a scan. SQL is ORM-only (no string interpolation). |
| Bid rules / mass assignment | `BidCreate`/`BidUpdate` are `extra="forbid"`; the server sets `developer_id`, `status`, `ineligible_reasons`. One ACTIVE bid per project (partial unique); bids are placed/edited only while BIDDING (409 otherwise), enforced in the service **and** by the RLS `WITH CHECK (project_is_bidding(...))`. Rate limit 20/hour. Prices are integer paisa with bounds. |
| Eligibility preview | The dry-run builds a `BidInput` from the **caller's own** snapshot/skills/evidence (which they may read) and returns only their own standing; it never exposes other bids or developers. |
| Reputation snapshots | Public read for any authenticated user (a public value); SYSTEM-only to write (seed / Phase 6 engine), verified by RLS test. The "seeded" marker is suppressed in production. |
| Authorization matrix | Every new route has a matrix entry; a developer on the client bids view → 403, a foreign project → 404, anonymous → 401. The matrix test fails if a route is added without an entry. |

## Findings fixed during the phase

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Medium | Eligibility computed in the client's (or SYSTEM's) own context read nothing for other developers' private skills/evidence under RLS, so every bid looked ineligible — and the deadline job could not transition a project. | **Fixed (D50):** evaluate eligibility in a SYSTEM session with minimal, additive SELECT/transition policies for the worker role; owner policies unchanged; the web role still cannot assume SYSTEM (tested). |
| 2 | Low | `/projects/search` and `/projects/recommended` were shadowed by `/projects/{project_id}` (router order), returning 422/403 for the wrong reasons. | **Fixed:** the marketplace router is registered before the projects router; covered by the authz matrix. |
| 3 | Low | WebKit can expose a cookie set by a `fetch` response to `document.cookie` a moment late, so the first unsafe request after `GET /auth/csrf` sometimes sent an empty `X-CSRF-Token` and was rejected (fail-closed, but it broke sign-up). | **Fixed (D53):** `GET /auth/csrf` also returns the token in an `X-CSRF-Token` response header (`Cache-Control: no-store`); the client uses it, sharing one fetch across concurrent callers. Same-origin JS could already read the cookie, so nothing new is exposed; the cookie must still be present and equal (double submit and Origin check unchanged; tested, including an echoed token without its cookie → 403). |
| 4 | Low | After registering, the automatic sign-in sent no CAPTCHA; on a shared IP with recent failed sign-ins the server (correctly) required one and the new user was stuck. | **Fixed (D53):** the follow-up sign-in solves the check and retries only on `captcha_required`; the server rule is unchanged. |
| 5 | Low | A NUL byte (or other control character) in the search text or skill filters of `GET /public/projects` and `/projects/search` reached PostgreSQL, which rejects NUL in text → 500 (found by schemathesis). No data exposure, but anyone could trigger server errors; the skill filter list was also unbounded. | **Fixed (D53):** the search service strips control characters, NFC-normalises and trims the text and skill names (empty values dropped) and refuses more than 20 skills (422); tests for both endpoints plus an injection corpus. |

## Follow-ups after the external review (D54, 2026-10-22)

| # | Severity | Finding | Status |
|---|---|---|---|
| 6 | Low | A bid's `portfolio_item_ids` were not checked: a developer could attach another developer's portfolio item ids, and the client's view would then list those items' titles under the wrong bidder. | **Fixed:** create and edit accept only the bidder's own items (422 otherwise, duplicates refused); tested with a foreign, an unknown and a duplicate id. |
| 7 | Low | Bidding closed only when the deadline job changed the status, so a late or stopped job let bids be placed, edited or withdrawn after the deadline. | **Fixed:** every bid write and the preview also require `now < bidding_deadline` (409); search/recommendations hide closed projects; tested with a passed deadline while the status is still BIDDING. |
| 8 | Low | Sign-in used strict `EmailStr`, which refuses reserved domains, so the seeded demo accounts (`@devsync.local`) could not sign in at all (availability, not exposure). | **Fixed:** login/forgot use a syntax-only lookup type; registration stays strict; malformed and control-character input still 422 (tested); `make demo-preflight` signs in as the demo client. |

New surfaces reviewed (no new high or medium findings):

| Area | Conclusion |
|---|---|
| Too-few-bids actions (`/projects/{id}/bidding-terms[/preview]`) | New `project.terms` policy: clients only (developer → 403, another client → 404, anonymous → 401; matrix entries added). The service checks ownership and the BIDDING state, `extra="forbid"` refuses mass assignment (`status` → 422), every rule is server-side (standards floor/ceiling, raise-only budget, reduce-only team, ≥ 2 people), If-Match prevents lost updates, and each change is audited with before/after. Preview runs in the same SYSTEM-session pattern as D50 after the ownership check and returns only counts. |
| Notifications to bidders | Written through a SYSTEM session (RLS allows only SYSTEM inserts); fixed text plus the recipient's own project data; links are app paths. |
| Explanations in the client view | Built from the same SYSTEM evaluation as before; the trace contains thresholds, the bid's own numbers and the bidder's skill-test score for the slot — data the spec shows the client (§13.5 #23). The developer's preview never ranks against other bids (no NOT_SHORTLISTED; tested), so sealing holds. |
| Search and recommendations | Skill-name matching adds an ORM subquery under `plainto_tsquery`; cursors name their sort and are validated (another sort's cursor → 422). The recommendation cache is keyed per developer, so one developer's list is never served to another; it fails open without Redis. |
| Test-only routes (close bidding, skill evidence, reputation) | Mounted only when `DEVSYNC_ENV=test` (create_app refuses otherwise) and not in the OpenAPI schema, like the Phase 1 seed routes. |
| Hero software-WebGL probe | Reads only the renderer string of a throwaway context and releases it; no data leaves the page. |
