# Security review — Phase 7 (team formation)

- **Date:** 2026-11-22
- **Reviewer:** Claude Code (`/security-review` method on `main...phase-7`), with Raisa Tabassum.
  The review traced every new route, RLS policy, definer helper, trigger, service read path and
  frontend rendering path against the Phase 1–6 patterns; findings filtered at confidence ≥ 8/10.
- **Scope:** migrations `0013_audit_chain_order` and `0014_team_formation` (`formation_runs`,
  `bid_explanations`, `teams`, `team_members`, `invitations`); `algorithms/fitness.py`,
  `bpso.py`, `exact_solver.py`, `fairness.py`, `explain.py`, `formation.py`, `baselines.py`;
  `services/formation.py`, `formation_runner.py`, `jobs_api.py`; `core/job_events.py`,
  `core/task_queue.py`, the `SSE_PATHS` timeout exemption, the `loop_redis` dependency; the jobs
  `formation.run`, `formation.explanations`, `formation.verify`; every formation and jobs route
  with the `formation.*`, `bid.explanation` and `job.read` policies; the Nginx SSE location; the
  test-only `start-forming`, `execute` and `explanations` routes; the stage-2 seed change; the
  team formation screen, the "why not selected" card and the homepage figures.
- **Tester's human check (spec §14.22):** _pending_ (Sara): as two clients, confirm neither can
  open the other's formation runs (404); as a non-selected developer, confirm the explanation
  names nobody and another developer's explanation is 404; open a run's event stream from
  another origin and confirm 403.

Unresolved high findings: 0

## Result of the review

No high- or medium-confidence vulnerabilities were found. The §14.13 row 7 controls hold.

| Area | Conclusion |
|---|---|
| Who may run, read and confirm | Start and confirm need the client role and project ownership (404 otherwise); reading needs the project's client or an admin; the SYSTEM sessions used to build the snapshot and to write the run, team and bids open only after those checks (D50 pattern). Confirm re-locks the project and re-checks every chosen bid inside its transaction. Admin verify needs `admin.access` and a step-up. Authz matrix covers every route. |
| Integrity of a run | The seed is chosen by the server (a body `seed` is 422; every request body is a `StrictRequest`). A trigger refuses any change to a run's inputs (snapshot, params, seed, settings version) and any delete, even for SYSTEM, and the app roles have no DELETE/TRUNCATE grant. All formation tables are SYSTEM-write with `is_system()` (worker login role): a web connection claiming SYSTEM is refused (tested). |
| Sealed bids | Explanations are readable only by the bidder and admins (`bid.explanation` + RLS `is_bid_owner`); a selected or unknown bid is 404. The explanation carries the selected bid's days and price in the same slot, as §9.8 asks, but no id, name or person (tested by scanning the response). Runs, with names and prices, are visible only to the project's client and admins. |
| Definer helpers | `is_team_member`, `is_team_client`, `invitation_visible`, `is_bid_owner` pin `search_path`, are revoked from PUBLIC and the read-only role, and granted only to the app and worker roles. RLS is ENABLE + FORCE on all five tables (`check_rls.py`: 0 unprotected). |
| Job status and the event stream | Requester or admin only (service + `jobs_select` RLS; system jobs 404). The stream refuses a foreign `Origin` or a cross-site `Sec-Fetch-Site` (403), carries only allow-listed keys (no names or prices can be published), validates `Last-Event-ID` (≤ 6 digits), re-reads the job in the caller's own session, and holds no DB connection. The route-timeout exemption matches exactly the two stream paths (narrower than the earlier "ends with /stream"); the Nginx location is a single anchored regex. |
| Task queue | Services queue only names from a fixed table with server-generated UUID arguments; nothing a client sends chooses the code that runs. |
| Injection and encoding | ORM/Core with bound parameters; the admin cursor decodes to a typed time + UUID (garbage is 422). The UI renders all values as React text; charts set numeric attributes and token classes only; no `dangerouslySetInnerHTML`, no injected styles (CSP unchanged; the swarm animation is a stylesheet utility). |
| Test-only routes | Mounted only when `DEVSYNC_ENV=test`; `assert_no_test_routes` refuses startup otherwise. |

## Findings fixed during the phase

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Low (availability / correctness) | The sync `redis_client` dependency ran in a worker thread and got the loop-less Redis client, which belongs to whichever event loop first used it. | **Fixed:** an async `loop_redis` dependency gives each loop its own client. |
| 2 | Low (correctness of a sealed read) | The first snapshot build ran Algorithm 1 in the client's session, where RLS hides bidders' skills, so every bid looked like a skill mismatch. | **Fixed:** evaluated in a SYSTEM session after the ownership check, as the Bids view does (D50, D106). |
| 3 | Low (data exposure, defensive) | The route timeout spared any path ending in `/stream`. | **Fixed:** exact `SSE_PATHS` regex (tested both ways). |

## Accepted, not changed

- `POST /formation-runs/{id}/verify` and an admin's `GET /formation-runs/{id}` are outside
  `/api/v1/admin/`, so Nginx's admin IP allowlist doesn't cover them. They still need an admin
  session with TOTP, and verify a step-up (confidence it matters: 3/10). The admin console page
  (Phase 12) will read runs through `/admin/formation-runs`.
- The selected bid's price and days in one's own slot are disclosed to a non-selected bidder by
  design (§9.8's concrete hint); nothing else about other bids is.
- A stream that is accepted but never iterated holds its slot until the 31-minute expiry.
