# Security review — Phase 9 (the workspace and monitoring)

- **Date:** 2026-11-28
- **Reviewer:** Claude Code (the `/security-review` method on `main...phase-9`), with Sara Binte
  Shafayet. Every new route was traced from its `authz.py` policy, through
  `services/workspace.load` and the service's object checks, to the row-level security (RLS) of
  migration 0016. Findings were filtered at confidence ≥ 8 out of 10.
- **Scope:**
  - **Migration `0016_workspace`:**
    - 13 tables with RLS ENABLE and FORCE;
    - the helpers `is_participant`, `is_project_lead`, `is_active_project_member` and
      `is_own_member`;
    - the `record_activity()` definer;
    - the guard, revision, append-only and `thread_last_post` triggers;
    - `file_access()` and the policies on project files.
  - **Services:** `workspace`, `tasks`, `checkins`, `comments`, `discussion`, `project_files`,
    `files`, `monitoring`, `my_projects`, `notifications`, `notification_prefs`, `outbox`,
    `activity`, and the Phase 9 hooks in `team`.
  - **Routes:** every one in `api/v1/{tasks,checkins,comments,discussion,project_files,
    monitoring,notifications}.py`.
  - **Core:** `core/{authz,cache,middleware,notification_types}.py`, and `uploads/pipeline.py`
    (PROJECT_FILE).
  - **The rest:**
    - the notification stream's Nginx location;
    - the DAST scripts `zap_scan.py` and `zap_session.py`;
    - the workspace tabs, `Comments`, `linkify`, `VirtualList` and the notification switches.
- **Tester's human check (spec §14.22):** _pending_ (Sara). As a member of one project:
  - open another project's `/w/{id}/tasks` and its API (404);
  - move a task assigned to someone else (403);
  - as the client, try a task move by API (403);
  - post a comment with `<script>alert(1)</script>` and a `javascript:` link, and check both
    show as text;
  - upload an `.html` renamed `.png` (422);
  - open `/api/v1/notifications/stream` from another origin (403);
  - as a member, scan the dashboard response for `_paisa` (none).

Unresolved high findings: 0

## Result of the review

No high- or medium-confidence vulnerabilities were found. The §14.13 row 9 controls hold.

| Area | Conclusion |
|---|---|
| Who gets in | `load()` admits the client and the team's ACTIVE (reading: also COMPLETED) members, and answers 404 to anyone else, before any read or write. Writing needs an ACTIVE member or the client, and an IN_PROGRESS project. Admins get 403 on conversations and files. Lead powers need an ACTIVE lead row of that project. RLS repeats the participant rule on all 13 tables. |
| Tasks | Every task, milestone and dependency lookup is compared with the loaded project. Dependencies stay in one milestone, and the guard trigger repeats that. Moves need the assignee or the lead (never the client), the neighbours must be in the same column, and `If-Match` is required. |
| Evidence | URLs are `https://` only (schema and CHECK), PR links match the GitHub pattern, and nothing is fetched. File evidence must be a live project file of the same project (service and trigger). Evidence is append-only. |
| Comments and discussion | The target's project is resolved under RLS before `load()`. Replies stay on the same target or thread. Mentions are filtered to participants. Only the author edits (for 15 minutes) or deletes. Revisions are readable by admins only. Bodies are rendered as React text; `linkify` emits text segments and accepts only `https:` URLs without credentials. |
| Check-ins | Posted only as the caller's own member row (`is_own_member` in RLS). The week and the on-time flag are computed by the server. |
| Files | Upload, list and delete go through `load()`. Delete needs the uploader or the lead, and `files_identity_immutable` lets the lead change only `deleted_at`. `file_access()` serves a project file only to current participants, never once deleted. Types are checked by signature, images re-encoded, names sanitized with the detected extension, downloads served as attachments. The restrictive INSERT guard blocks files for foreign projects. |
| Money and role shapes | Members get `DashboardForMember` and forecast snapshots with no paisa fields. BUDGET and AUTO_APPROVAL_SOON are filtered by the service and by RLS. The cache key includes the shape. `my_projects` reads only the caller's own rows. |
| Live notifications | Each stream subscribes only to `notif:{caller}`. The replay runs under the caller's own RLS context. Events carry `{id, type, title}`. A foreign `Origin` or a cross-site `Sec-Fetch-Site` gets 403. Streams are capped per user, and the Nginx location matches the exact path. |
| Definers and RLS | Every definer pins `search_path`. `record_activity` takes the actor from `app_uid()` and refuses non-participants, unknown types and subjects outside the project. EXECUTE on trigger functions is revoked from the runtime roles. Append-only tables lose UPDATE, DELETE and TRUNCATE. Preferences are kept to their owner's rows. |
| DAST tooling | The scan's session is a throwaway test-stack user with a random password per run. Its cookie is redacted from ZAP's output and the reports, and the plan file is deleted after the scan (checked: no cookie value in `runs/zap/`). |

## Observations below the bar (not vulnerabilities)

- **The `tasks` UPDATE and DELETE policies allow any ACTIVE member.** The service narrows this to
  the lead and the assignee, and no route bypasses the service. Narrowing the policy itself is
  defence in depth for a later phase.
- **The revision trigger's "target never changes" check runs only when the body changes.** The
  services only ever change `body` and `deleted_at`, so it can't be reached. Worth moving out of
  that branch the next time the trigger is touched.
