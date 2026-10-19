# Security review — Phase 4 (Projects and the CPM planner)

- **Date:** 2026-10-19
- **Reviewer:** Claude Code (`/security-review` method on `main...phase-4`), with Salwa Baki.
  A manual review pass read the security-critical surfaces (authorization registry, migration
  `0005` RLS/triggers/definers, project service guards, repository queries, routes, and the new
  frontend screens and API-client change) against the established Phase 1–3 patterns; findings
  filtered at confidence ≥ 8/10.
- **Scope:** migration `0005_projects_planning` (7 tables, RLS policies, SECURITY DEFINER
  `is_project_client`/`project_visible`, baseline-immutability and publish-guard triggers), the
  pure CPM/forecast algorithms, project schemas/repository/service/routes, the authorization
  policies for projects and payment verification, optimistic concurrency (`If-Match`), and the
  Phase 4 frontend (create-project wizard, plan page, My Projects, SVG Gantt/DependencyGraph/
  CpmTable, and the `RequestOptions.headers` addition to the API client).
- **Tester's human check (spec §14.22):** _pending_

Unresolved high findings: 0

## Result of the review

No high-confidence (≥ 8/10) vulnerabilities were found.

| Area | Conclusion |
|---|---|
| Authorization | Deny-by-default registry extended with `project.create/write/read/cancel` and `payment.verify`. Role checks are explicit; object ownership is deferred to the service and returns 404 (never 403), so a project's existence is not leaked to non-owners. The authz matrix test covers all 14 operations (anon → 401, wrong role → 403, foreign object → 404). |
| Object ownership / IDOR | `_load_for_read` requires `client_id == uid` or admin; `_load_for_write` requires `client_id == uid` only (admins cannot edit another client's draft); `cancel` allows owner or admin. Every non-match raises `NotFoundError`. Enforced again by RLS and proven by `tests/integration/test_rls_projects.py` and the per-endpoint IDOR tests. |
| Row-level security | ENABLE **and** FORCE on all seven tables. `projects` SELECT is gated on `status <> 'DRAFT' OR client_id = app_uid() OR is_admin()`; INSERT `WITH CHECK (client_id = app_uid() AND app_role() = 'CLIENT')`; UPDATE/DELETE scoped to the owner. Child tables gate on `project_visible()` / `is_project_client()`; the plan baseline is owner-or-admin for SELECT, owner-only for writes. Both SECURITY DEFINER helpers are `STABLE`, pin `SET search_path = pg_catalog, public`, and have EXECUTE revoked from `PUBLIC` and `devsync_readonly`. |
| SQL injection | None. The repository and service use SQLAlchemy ORM constructs exclusively; the only f-string SQL (`REVOKE ALL ON FUNCTION {fn} …`) interpolates a hardcoded migration-time list of function names, never user input. |
| Optimistic concurrency | `PATCH /projects/{id}` requires an `If-Match` integer version; a stale write raises `VERSION_CONFLICT` (409). The frontend's new `RequestOptions.headers` is populated in code with `If-Match` only — same-origin, not user-controlled — so there is no request-header injection. |
| CPM / forecast | Pure functions (no DB, network, clock or `eval`). User-supplied milestone `key`/`name` values are used only as dictionary keys and echoed back in JSON, which React renders as text. No injection sink; cycles raise a typed 422. |
| Publish guards | `DRAFT → BIDDING` enforces a verified payment method (D39), at least one slot, Σ milestone shares = 100%, an acyclic plan, and a schedule-risk acknowledgement when CPM > deadline (D40) — in both the service and the `guard_project_publish` trigger. Baseline identity and content are frozen by `guard_baseline_immutable`. |
| Payment verification (D39) | `POST /me/payment-method/verify` is CLIENT-only, idempotent, and acts solely on `ctx.uid`; there is no path to verify another account's method. |
| Frontend | React/TSX with no unsafe DOM sinks (no `dangerouslySetInnerHTML`, `eval`, or external URLs). The SVG charts render user text through `<text>` nodes (escaped by React). The single inline `style` is a dynamic bar width, which the existing CSP already permits (matching `Progress`/`StillsPage`). The `TagPicker` uses native buttons with `aria-pressed`. |

## Findings fixed during the phase

None. No security findings required a fix during Phase 4; the new surface reused the Phase 1–3
patterns (deny-by-default authz, FORCE RLS with pinned-`search_path` definers, strict request
schemas with 422 on unknown fields, ORM-only queries) without deviation.
