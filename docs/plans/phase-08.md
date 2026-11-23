# Phase 8 — Invitations, team lead, team repair (plan)

> On approval this file is saved verbatim as `docs/plans/phase-08.md` (first commit on branch
> `phase-8`, created from `main` = `eabf76f`). Owner: Raisa Tabassum (with Claude Code).
> Spec: §1.6 (lead selection), §2.2, §7.3–7.4, §8, §9.9, §9.10, §9.17, §10.1–10.4, §11, §12,
> §13.5 #9/#12/#18/#25/#33, §14.4–14.8, §14.13 row 8, §14.15, §16, §17 Phase 8, §18.4.
> Binding input: `phase-08-start-prompt.md` Step 5 (decisions 1–19 → **D118–D136**, in order).
> Next free decision after those: **D137**.

**Skills for the frontend work:** `devsync-ui` (+ `references/components.md`) and
`frontend-design`, loaded before any screen code; `devsync-ui` wins.

## Context

Phase 7 forms a team and records **unsent** invitations (D108); nothing lets a developer answer,
a lead be chosen, the project start, or a team recover from a decline. Phase 8 turns a formed team
into a started project with a client-confirmed lead (§1.6), and repairs it gracefully when people
decline, expire, leave or are removed (§9.9). It is on the Demo 2 walkthrough (7 Dec), so nothing
moves to a later demo. Target: about four working days, correctness first.

## Decisions to record (D118–D136 = prompt decisions 1–19, verbatim in substance)

D118 root milestones → ACTIVE at start via one guard `milestone_may_activate()` (Phase 10 tightens
to FUNDED) · D119 what "start" does in one transaction (guard, start date = max(planned, today
Dhaka), shifted reservation window with availability re-check → 409 naming the member, baseline
`approved_by_lead`, team ACTIVE, notices; explicit client "Start project"; §17's "workspace
defaults" are not created — Phase 9 fills the shell) · D120 workspace shell `/w/:projectId/team` ·
D121 removal requests (basis function `member_inactive_days()` returns "no signal" in Phase 8 →
409; tests stub it) · D122 notifications read API + page + bell badge · D123 unsent invitations
sent on confirm and by `lifecycle.expire` · D124 availability re-check on accept → 409
`UNAVAILABLE` · D125 ≤ 10 pending invitations per developer, enforced at candidate choice
(`TOO_MANY_PENDING_INVITATIONS`), race → 409 · D126 reopen slot 48 h (≤ 2) · D127 raise budget ·
D128 repair uses current data frozen per proposal; `NOT_SELECTED → SELECTED` added to the bid
transition table; repair job `requested_by` = the client · D129 affected milestones · D130 team
visibility (`is_team_member` counts INVITED/ACTIVE/COMPLETED; role-shaped member models) · D131
lead ranking inputs · D132 the lead role and its caps (named constants) · D133 test-only repair /
expire / set-expiry routes · D134 the extra endpoints · D135 cancellation (TEAM_PENDING free and
fully released; IN_PROGRESS 409 until Phases 10/12) · D136 account changes during a team.

Points the prompt left open, resolved with my proposals ("use whatever is told"):
- **D137 · One bid per developer per project on a reopened slot.** The DB index
  `one_standing_bid_per_developer` covers only ACTIVE/INELIGIBLE, so the bid service refuses a
  reopened-slot bid from anyone with a non-WITHDRAWN bid on the project (D49 kept: withdrawn may
  bid again). No schema change.
- **D138 · Repair impact arithmetic (§9.9).** Each affected milestone's duration is scaled by
  candidate days ÷ departed member's days (ceil, ≥ 1); CPM (`cpm.compute_cpm`) before start, and
  `forecast.forecast` after start, are recomputed; delay = new finish − baseline duration;
  budget delta = Σ team price with the candidate − C (A10). Worked example in `ALGORITHMS.md` and a
  hand-computed test.
- **D139 · The stage-2 seed's golden file moves to `backend/scripts/seed_data/`.** `make demo-up
  STAGE=2` fails in the production image (no `tests/` there) — broken since Phase 6, unseen
  because the gate seeds in the tests container. The test reads it from the new place.
- Decision 7 detail (in D124): the re-check sums only CONFIRMED reservations on *other* projects
  overlapping the period; the member's own TENTATIVE one never counts.
- Decision 19 (D136): self-deletion and admin suspension don't exist yet (BACKLOG: Phase 12); the
  rule is recorded for Phase 12 (refuse while ACTIVE in IN_PROGRESS; pending invitation →
  declined; TEAM_PENDING ACTIVE member → left). Nothing is built for it now.

## Data — migration `0015_team_lifecycle` (style of 0014, full downgrade)

| Table / change | Columns | RLS (ENABLE + FORCE; writes SYSTEM-only `is_system()`) |
|---|---|---|
| `lead_change_requests` | team_id, requested_by, reason (20–500), suggested_member_id NULL, `status lead_change_status` (PENDING, APPROVED, REJECTED, WITHDRAWN), decided_by, decided_at, decision_reason; partial UNIQUE (team_id, requested_by) WHERE PENDING | team's client + its ACTIVE members (service narrows a member to own) + admin |
| `repair_proposals` | team_id, departed_member_id, `status repair_status` (COMPUTING, READY, NO_CANDIDATES, CHOSEN, SUPERSEDED, CANCELLED), impact jsonb, candidates jsonb, reasons jsonb, chosen_bid_id, candidate_snapshot, params, seed, settings_version, job_id; partial UNIQUE one open (COMPUTING/READY/NO_CANDIDATES) per departed member | client + admin; inputs immutable + no delete (trigger like `formation_run_guard`) |
| `member_removal_requests` | team_member_id, requested_by, reason (20–500), basis (`INACTIVITY`/`DISPUTE`), `status` (PENDING, APPROVED, REJECTED), decided_by, decided_at, decision_reason | client + admin |
| `team_members.lead_declined_at` | timestamptz NULL | — |
| `project_slots.reopened_until`, `reopen_count` | timestamptz NULL, smallint 0–2 | — |
| `is_team_member()` | counts only INVITED/ACTIVE/COMPLETED (downgrade restores 0014's) | — |

Enums created complete up front (D38). Add the new user-referencing tables to `USER_SCOPED` in
`tests/integration/test_demo_reset.py`; `check_rls.py` 0 unprotected; `make erd`.

## Backend — algorithms (PURE, ≥ 95 % coverage)

- `algorithms/lead.py` — `recommend_lead(members, excluded)`: ACTIVE members by X_m desc,
  completed projects desc, C desc, earlier `responded_at`, developer id; skips anyone with
  `lead_declined_at` or excluded; `reason(m, led)` → "Highest teamwork capacity: 86; led 2 past
  teams" (clause omitted at 0). Property test: the pick always has maximal X_m.
- `algorithms/repair.py` — `rank_replacements(problem, locked, open_slot, k=10, top=3, solve)`
  reusing `fitness`, `exact_solver.solve_exact` (locks honoured) or PSO through `Problem.locked`;
  marginal-score prefilter; newcomer minimum kept if a newcomer candidate exists else relaxed with
  a note; no-candidate reasons. `repair_impact(...)` (D138) over `cpm`/`forecast`.

## Backend — services, jobs, routes

- `services/team.py` — team read (role-shaped: `TeamForClient` vs `TeamForMember`, D130), send
  invitations (`sent_at`, `expires_at = sent_at + invite.expiry_hours`; "You were selected" in-app
  + email, replacement variant), accept (D124 re-check; member ACTIVE, bid ACCEPTED, reservation
  CONFIRMED; replacement during IN_PROGRESS joins with today → planned finish) / decline (member +
  bid DECLINED, reservation RELEASED, repair queued), expire (in `lifecycle.expire`; lock + re-check,
  race-safe), lead choose / decline role / change with reason, lead-change requests (create,
  approve → outgoing lead normal + recommendation with suggested member pre-selected, reject with
  reason, withdraw; caps as constants D132), start project (D118/D119 through the project
  transition table, 409 + `allowed_actions`), leave (reason; lead → recommendation), removal
  requests (D121) + admin approve/reject (step-up), cancel TEAM_PENDING (closing the gap in
  `projects.cancel`, D135).
- `services/repair.py` — create proposal (SYSTEM snapshot: eligible bids for the open slot that
  weren't declined, not current members, available now, Algorithm 1 under the confirmed run's
  standards, ≤ 10 pending invitations), supersede the open one, queue `formation.repair`
  (`requested_by` = client, D128), choose (replacement member `is_replacement`, invitation sent,
  TENTATIVE reservation, bid `NOT_SELECTED → SELECTED`, "selected as a replacement"; earlier
  explanation marked superseded), reopen slot (D126), raise budget (D127, `If-Match`, audit old/new,
  recompute).
- `services/formation_runner.py` gains `execute_repair`; `build_snapshot` gains the 10-pending
  exclusion (D125). `formation_check.py` proves the D116 team and homepage figures are unchanged.
- `services/notifications.py` read side: list (cursor), read, read-all, unread count; own rows only
  (RLS `notif_select/notif_update` already scope them); `link_path` validated by `core/redirects`.
- `services/bids.py` — reopened-slot bids outside BIDDING for that slot only (D126, D137); search
  shows "1 open place" without bid data.
- Jobs: `formation.repair` in `core/task_queue.TASKS` (default queue, 60 s, 1 retry) + RQ entry in
  `jobs/formation_jobs.py`; `lifecycle.expire` (`email_jobs.expire_records`) gains invitations
  (send unsent of TEAM_PENDING teams, expire overdue) and reopened-slot windows (close → repair).
- Emails: new `integrations/email.py` `TEMPLATES` — `invitation_selected`,
  `invitation_replacement`, `project_started`, `team_lead` (lead chosen / changed); autoescaped,
  no other users' private data; checked in Mailpit.
- Authz: one `authz.py` policy per action, lead powers scoped per project, admin removal routes
  under `/admin/` (404 for non-admins); authz matrix rows for every route.

| Method & path | Who | Notes |
|---|---|---|
| GET `/projects/{id}/team` | client, members (INVITED/ACTIVE/COMPLETED), admin | role-shaped; others 404 |
| POST `/invitations/{id}/accept` · `/decline` | invitee | 409 expired/answered/unsent/UNAVAILABLE; others 404 |
| POST `/projects/{id}/team/lead` | client | `If-Match`; ACTIVE member only |
| POST `/projects/{id}/team/lead/decline` | the lead | before or after start |
| POST `/projects/{id}/lead-change-requests` | ACTIVE member | reason 20–500; caps |
| POST `/lead-change-requests/{id}/approve` · `/reject` · `/withdraw` | client · client · requester | reject needs reason |
| GET `/projects/{id}/repair` | client, admin | latest proposal incl. COMPUTING; devs 404 |
| POST `/repair-proposals/{id}/choose` | client | body `bid_id` from the proposal |
| POST `/projects/{id}/slots/{slot}/reopen` | client | from NO_CANDIDATES proposal, ≤ 2 |
| POST `/projects/{id}/budget` | client | `If-Match`; ≥ current + shortfall |
| POST `/projects/{id}/start` | client | `If-Match`; D119 |
| POST `/team-members/{id}/leave` | that member | reason 20–500 |
| POST `/team-members/{id}/removal-requests` | client | basis INACTIVITY → 409 until Phase 9 |
| GET `/admin/removal-requests` · POST `/admin/removal-requests/{id}/approve|reject` | admin, step-up | |
| GET `/me/invitations` · GET `/me/teams` | developer · client | |
| GET `/notifications` · POST `/notifications/{id}/read` · POST `/notifications/read-all` · GET `/notifications/unread-count` | session | own rows |
| test-only: run repair now, run `lifecycle.expire` now, set an invitation's `expires_at` | `DEVSYNC_ENV=test` | D133 |

All contract-first (schemas + examples + declared errors), `StrictRequest` bodies (mass assignment
of `is_lead`, `status`, `price_paisa`, `expires_at`, `is_replacement`, `team_id` → 422).

## Frontend (devsync-ui + frontend-design; four states; light/dark; 375–1440)

- Developer dashboard (#9): invitation banners with countdown (static text for screen readers,
  amber < 6 h, minute ticks under reduced motion), Accept / Decline (confirm, optional reason),
  outcome; "You are team lead" + decline role; cards for started projects → `/w/:id/team`.
- Client Team `/client/projects/:id/team` (#25): invitations + statuses ("can't accept: fully
  booked"), lead recommendation card + selector + "Start project" (disabled with reason), repair
  panel (impact, top-3 comparison, Invite replacement, Reopen slot, Raise budget) following the
  job's SSE (D107), removal request.
- `/client/teams` list (replaces the D110 placeholder); links from client dashboard and formation
  page ("Manage your team").
- `/notifications` (#18) + bell unread badge (focus + every 60 s while visible); nav marker dropped.
- Workspace shell `/w/:projectId` with a real Team tab (#33) and "arrives in Phase 9" tabs;
  client + members only (404 otherwise): members, slot, lead badge, reputation 0–100, hours/week,
  lead-change request, leave (reason + confirm).
- Bid detail timeline Selected → Accepted / Declined / Expired, replacement selection,
  superseded "why not selected"; marketplace "1 open place".

## Seed and gate

- D139 golden file move. Stage 2 adds the §18.4 repair-demo project through the real services
  (publish → bids → run via `formation_runner` → confirm → invitations sent → three accept → one
  declines → repair job → READY), dates and developers chosen so the ordering project's eligible
  bids, D116 team and the reputation golden fixture don't change; the seed asserts its end state;
  accounts printed; `demo-reset STAGE=2` < 30 s.
- `phase8_checks` = `phase7_checks` + scripted run → confirm → decline → repair ≥ 1 candidate on
  the ordering project + the seeded proposal READY + the named Phase 8 security tests.

## Tests (never happy-path-only)

Exactly the prompt's Step 7 list: lead ranking (property + one test per tie-break, newcomer
without snapshot, skip decliners, reason text); invitations (48 h from setting, accept just before
/ after expiry with `FrozenClock`, double answers, someone else's → 404, unsent can't be answered,
expiry idempotent, expiry-vs-accept race with exactly one outcome, 10-pending boundary, D54
boundary); reservations through every path; start guard/effects/refusal with no partial state;
lead flows incl. per-project lead powers; repair (locks, budget A10, ranking, hand-computed impact,
newcomer minimum, each no-candidate reason, reopen and raise paths, choose transition, job
requester = client); leave/removal/cancel incl. reason bounds 19/20/500/501 and IN_PROGRESS cancel
409; reopen/budget/notifications/snapshot exclusion; repair proposal immutability; repair perf
(`perf`: 10 candidates, 4 members < 5 s); security (authz matrix × all roles, IDOR on every id,
mass assignment, RLS for new tables and D130 visibility, response scanning for others' prices/days,
injection corpus on reasons, NUL/wrong types, schemathesis); E2E `phase8.spec.ts` (the §17 flow +
notifications); new screens in `screens.ts` / `stateful-screens.ts` with countdowns and dates
masked; FR-INV-1..5 in test names. Coverage ≥ 85 % backend / ≥ 70 % frontend; route chunks
≤ 150 KB gzip.

## Order of work

1. Plan file + D118–D139; D139 seed fix.
2. Migration 0015 + models + RLS/immutability tests.
3. Pure `lead.py`, `repair.py` + tests.
4. Services: invitations (send/accept/decline/expire), team read, lead flows, start, leave,
   removal, cancel; notifications read API; emails.
5. Repair service + job + reopen/budget + bid changes + test routes.
6. Routes, authz matrix, OpenAPI, frontend types.
7. Frontend screens; Vitest.
8. Seed repair-demo project, `phase8_checks`, E2E, stateful screens, visual baselines.
9. Docs (API, SECURITY, ALGORITHMS, BACKLOG, FR_MAPPING, OWNERSHIP, PROGRESS), `/security-review`,
   `docs/security-reviews/phase-08.md`; local checks; push for the gate.

## Verification

Per step: `pytest -m "unit or property"`, vitest. Before push (D117 lessons):
`python3 backend/scripts/phase_gate.py --phase 8 --only lint,types,static-security,forbidden,migrations`;
the placeholder grep (`arrives in Phase|Teams|Notifications|phase: 8`); backend suite in the test
stack; security suite; `make fuzz` on new endpoints; vitest; Phase 8 E2E + stateful screens on
Chromium; `make demo-reset STAGE=2` < 30 s with D116 team and golden reputations unchanged;
`formation_check.py` unchanged. After API changes: rebuild test image → `make openapi` →
`npm run api:types`. Gate step 16 and full-run timings: Taeen's native Linux laptop.

## Risks

- Size vs four days: the repair job and the Team screen are the long poles; lead flows and
  notifications are small. Nothing may move to Demo 3.
- Races (accept/decline/expiry/choose): row locks in a consistent order (project → team → member →
  invitation → bid → reservation) and in-transaction re-checks, with a concurrent test.
- Visual baselines change for the shell (nav markers); regenerate and review.
