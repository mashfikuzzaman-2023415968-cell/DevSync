# Security review — Phase 8 (invitations, team lead, team repair)

- **Date:** 2026-11-24
- **Reviewer:** Claude Code (`/security-review` method on `main...phase-8`), with Raisa Tabassum.
  Every new route was traced from its `authz.py` policy through the service's object check to the
  SYSTEM-session write and the RLS of migration 0015; findings filtered at confidence ≥ 8/10.
- **Scope:** migration `0015_team_lifecycle` (`lead_change_requests`, `repair_proposals`,
  `member_removal_requests`, `team_members.lead_declined_at`, `project_slots.reopened_until` /
  `reopen_count`, the narrowed `is_team_member()`, helpers `is_active_team_member`,
  `is_member_client`, `slot_is_reopened`, the widened `bid_insert`, the SYSTEM policies on
  milestones, slots and baselines); `algorithms/lead.py`, `repair.py`; `services/team.py`,
  `repair.py`, `notifications.py`, the Phase 8 changes in `formation.py`, `formation_runner.py`,
  `bids.py`, `marketplace.py`, `projects.py`; the `formation.repair` job and `lifecycle.expire`;
  the new email templates; every route in `api/v1/team.py` and `api/v1/notifications.py` with the
  Phase 8 policies; the test-only repair/expire/expiry routes; the stage-2 repair demo seed and
  `repair_check.py`; the client Team screen, Teams list, invitation banners, workspace Team tab,
  notifications page and bell.
- **Tester's human check (spec §14.22):** _pending_ (Sara): as a developer, try to accept another
  developer's invitation id (404); as a team member, open `GET /projects/{id}/team` and confirm no
  price or days of anyone appears; as a second client, open another client's repair proposal and
  try to choose one of its bids (404); mark another user's notification read (404).

Unresolved high findings: 0

## Result of the review

No high- or medium-confidence vulnerabilities were found. The §14.13 row 8 controls hold.

| Area | Conclusion |
|---|---|
| Answering invitations | `_load_answer` joins invitation → member → team and answers 404 unless the member is the caller, before any lock or write; `_check_answerable` refuses unsent, answered or expired ones. The availability re-check (D124) runs inside the same transaction under row locks taken in one order. |
| Lead powers | Choosing needs the project's client and an ACTIVE member of that team who hasn't declined; declining needs the caller's own ACTIVE lead row; lead-change requests need an ACTIVE member (a suggested member must be in the same team), approve/reject the client, withdraw the requester; another team's request is 404. Caps are constants (D132). |
| Start, leave, removal | Start needs the owner and `If-Match`; leave refuses anyone but that member (404); a removal request needs the client and is 409 until Phase 9 (D121); the admin removal routes need `admin.access` and, to decide, a step-up. |
| Team repair | Reading needs the client or an admin. `choose` accepts only a `bid_id` from the proposal's own candidates, built by the server from that project's slot, and re-checks the bid. `reopen_slot` takes a slot only from the caller's own project with an open NO_CANDIDATES proposal; `raise_budget` is owner-only, needs the shortfall and is capped. Proposal inputs are immutable and never deleted (trigger + revoked grants), so a ranking can't be altered after the fact. |
| Who sees what (D130) | Non-members get 404. Members get `TeamForMember`, whose schema has no price or days fields; they see only current teammates and their own requests. Repair and removal data exist only in the client/admin shape. Tested by scanning member responses for prices. |
| Notifications | Every query filters on the caller (and RLS keeps rows to their owner); another user's id is 404. `link_path` is passed through `is_safe_path` (one leading `/`, a known route) or null, so no external or `javascript:` target reaches `navigate`. |
| Reopened-place bids | Outside BIDDING, a bid is accepted only on a slot whose window is open; anyone with a non-withdrawn bid on the project (current members included) is refused (D137); all earlier bid rules still apply. Search shows only the count of open places, never bid data. |
| RLS and definers | New helpers are SECURITY DEFINER with `search_path` pinned and EXECUTE revoked from PUBLIC; every write on the new tables and the new UPDATE/SELECT policies on milestones, slots and baselines require `is_system()` (the worker login role; a web connection claiming SYSTEM is refused, tested). `check_rls.py`: 0 unprotected. |
| Email | The new templates use the escaping builder; payloads carry the recipient's own data, the project title, the role, the expiry and the lead's display name; links are `PUBLIC_ORIGIN` plus a fixed path. |
| Injection and encoding | SQLAlchemy builders with bound parameters only; reasons are bounded text rendered as React text; no `dangerouslySetInnerHTML`, `innerHTML` or `eval` in the new screens; CSP unchanged. |
| Test-only routes | The three new ones live in `test_seed.py`, mounted only when `DEVSYNC_ENV=test`. |

## Findings fixed during the phase

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Low (integrity) | Starting a project activated nothing: RLS silently refused SYSTEM updates on milestones, slots and baselines. | **Fixed:** explicit `is_system()` UPDATE/SELECT policies in 0015 (tested). |

Hardening decided in the plan rather than found in review: `is_team_member()` now counts only
INVITED, ACTIVE and COMPLETED members, so people who declined or left stop reading the team
(D130); a reopened-place bid is refused from anyone with a non-withdrawn bid on the project, which
the bid index alone wouldn't prevent after a NOT_SELECTED bid (D137).

## Accepted, not changed

- `bid_insert` checks `slot_is_reopened(slot_id)` but not that the slot belongs to the bid's
  `project_id`; the bid service only accepts the project's own slots, so the API cannot reach the
  gap (confidence it matters: 2/10). A later migration can add the slot–project check.
- A member sees teammates' reputation (0–100) and weekly hours, as §13.5 #33 asks; prices and
  days stay with the client.
- Removal for inactivity is refused until Phase 9 records activity (D121), so a client can't yet
  remove an absent member; leave and repair remain available.
