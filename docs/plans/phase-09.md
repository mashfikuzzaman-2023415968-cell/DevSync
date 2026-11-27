# Phase 9 — Workspace and monitoring (plan)

> On approval this file is committed as `docs/plans/phase-09.md` on branch `phase-9` (created from
> `main` = `f7fedc1`). Owner: Sara Binte Shafayet (with Claude Code).
> Spec: §1.6, §2.2, §7.5, §7.8, §7.9, §8, §9.1.4–9.1.6, §9.9–9.11, §10.1–10.4, §11, §12,
> §13.4–13.9, §13.14, §14.5–14.9, §14.13 row 9, §14.15, §15.1–15.4, §16, §17 Phase 9, §18.2 item 2.
> Binding input: `phase-09-start-prompt.md` Step 5 (decisions 1–19 → **D141–D159**, in order).
> Next free decision after this plan: **D173** (D172 = required `If-Match` on task writes).

**Skills loaded for the frontend work:** `devsync-ui` (+ `references/components.md`) and
`frontend-design`. They are loaded before any screen code, and `devsync-ui` wins wherever the two
differ: the app has one existing look, so this phase reuses its tokens and parts rather than
inventing a new one.

## Context

Phase 8 left a started project with a Team tab and eight "arrives in Phase 9" tabs. Phase 9 fills
that shell. The team plans and does its work (tasks, check-ins, comments, discussion, files,
evidence). The client watches progress and risk without being able to touch the work (§1.6). Every
action leaves an append-only evidence event that Phase 11 turns into Γⁿ and Γₘⁿ. No surveillance.
It is on the Demo 2 walkthrough (7 Dec): "lead creates tasks, members move them and post check-ins
→ client watches progress and sees a CRITICAL risk with the deadline impact". Estimate **5–6
working days**, demo path first (D159).

## Decisions

**D141–D159 = start prompt decisions 1–19** (recorded in `DECISIONS.md`, commit `7e1c632`):
- D141 scope edges (read-only Milestones tab; Payments "arrives in Phase 10"; FR-PROJ-5 deferred;
  FR-DEL-1 moves into Phase 9).
- D142 workspace access (`is_project_member`, `is_participant`; client may comment, post and
  upload; writes need `IN_PROGRESS`; members read the plan; admins read monitoring only).
- D143 tasks.
- D144 fractional positions.
- D145 check-ins.
- D146 comments and discussion.
- D147 project files.
- D148 task evidence.
- D149 activity events.
- D150 inactivity.
- D151 risk engine and monitoring.
- D152 forecast on the plan.
- D153 notifications stream and preferences.
- D154 Inventory seed.
- D155 test-only routes.
- D156 extra endpoints.
- D157 DAST.
- D158 phones and virtualization.
- D159 order of work.

**Mine while studying** (already in `DECISIONS.md`):
- **D160** — the tab bar follows §13.4's eleven tabs: Overview, Tasks, Timeline, Milestones, Team,
  Check-ins, Files, Discussion, Evidence, Risks, Payments.
- **D161** — the forecast's remaining time is computed exactly with `Fraction`, because float
  rounding makes `ceil` add a phantom day.

**Mine while planning** (recorded in `DECISIONS.md` as the first build commit):
- **D162 · One notification catalogue, preferences per §12 row.**
  - `app/core/notification_types.py` defines `NotificationType` (StrEnum). It covers every kind
    Phases 5–8 send plus Phase 9's new kinds, and each type maps to exactly one `Category`, which
    is a §12 row (table below).
  - `notification_preferences.type` stores the **category** key, so one switch in Settings covers
    a §12 row.
  - Defaults follow §12's columns; mentions default to email off (D153).
  - `notify()` takes a `NotificationType` and refuses any other value. A test checks every
    `notify` and `enqueue` call against the catalogue.
  - Rejected: a preference per type (about 30 switches nobody understands) and free strings (no
    check).
- **D163 · Preferences enforced in the two writers.**
  - `notify` becomes `async` (it reads the recipient's preference row) and skips the in-app row
    when it's switched off.
  - `outbox.enqueue` gains `user_id` and `notification_type`. The six account templates
    (`verify_email`, `reset_password`, `account_exists`, `account_locked`, `new_device`,
    `password_changed`) form the fixed `ACCOUNT_TEMPLATES` set, are always sent and take no type.
    Every other template must name a type, and its email is skipped when switched off.
  - A test lists every template and asserts it is either an account template or mapped to a type.
  - Rejected: a DB trigger that drops rows. It's invisible in code reviews and can't cover email.
- **D164 · Publish after commit.**
  - `notify` appends `(user_id, id, type, title)` to `session.info["notif_pending"]`.
  - A SQLAlchemy `after_commit` listener publishes the pending entries to Redis `notif:{user_id}`.
  - An `after_rollback` listener discards them.
  - A rolled-back change never reaches a browser, and no caller has to remember to publish.
  - Rejected: Postgres `LISTEN/NOTIFY`, because §15.2 names Redis pub/sub and it would hold a
    database connection.
- **D165 · Debounced evaluation that never loses the last event.**
  - Task and milestone events, after commit, do `ZADD NX mon:dirty <now> <project_id>`.
  - A scheduler job `monitoring.flush` runs every 30 s. It enqueues `monitoring.evaluate` for every
    project whose score is at least 30 s old and removes exactly that member with that score
    (`ZREM` guarded by a Lua compare).
  - An event during an evaluation re-adds the project, so the next flush evaluates again.
  - Worst case ≈ 60 s from the last event; the 15-minute sweep stays as the backstop.
  - Rejected: `enqueue_in`, because no RQ scheduler runs (spec §11, `jobs/scheduler.py`).
- **D166 · Workspace rows carry `project_id`.**
  - `tasks`, `task_dependencies`, `task_evidence`, `comments`, `checkins`, `discussion_threads`
    and `discussion_posts` store `project_id NOT NULL`.
  - A guard trigger checks it matches the parent (milestone, task, thread or team), and it is
    immutable.
  - Why: RLS policies become one helper call per row (`is_participant(project_id)`) instead of
    joins, and the §7.9 queries stay index-only.
  - Rejected: joins inside every policy (slow, and easy to get subtly wrong).
- **D167 · `activity_events.subject_id`.** A nullable column holding the member the event is
  about, when that differs from the actor or there is no actor (for example `checkin.missed` and
  `member.left` written by SYSTEM). The Evidence tab and Phase 11 aggregate on it, and `data` keeps
  no user ids beyond mentions and replies. Rejected: putting the subject in `data`, which can't be
  indexed or constrained.
- **D168 · Evidence kinds and immutability.**
  - `FILE` references any live project file of the same project.
  - `SCREENSHOT` references an **image** project file.
  - `LINK` and `PR` carry an `https://` URL.
  - Evidence rows are immutable: there's no edit or delete (they are reputation evidence, like
    check-ins), and the 20-per-task cap counts them.
  - Rejected: a URL for screenshots, which would mean fetching or trusting remote images.
- **D169 · Comment revisions are written by a trigger and read by nobody but the admin.**
  - A `BEFORE UPDATE` trigger on `comments` and `discussion_posts` copies the old body into the
    revisions table (a `SECURITY DEFINER`, pinned `search_path`).
  - Participants see only the "edited" label. That keeps deleted and earlier text private (D146)
    without per-row rules.
  - Rejected: showing the edit history, which isn't in §13.5 and leaks text the author replaced.
- **D170 · `make seed-demo DAY=N` without `STAGE` means stage 2** (§17's literal command). `DAY`
  with `STAGE=1` is refused, because stage 1 has no Inventory project. `DAY` must be 3–20; outside
  that range the history doesn't fit.
- **D171 · The two new dependencies, pinned** (completes D157 and D158):
  - `@tanstack/react-virtual` **3.14.26**, published 2026-11-03 (24 days old). Its only
    dependency is `@tanstack/virtual-core` (same family, with no dependencies of its own). The
    brief said "no dependencies"; this one transitive package is recorded.
  - ZAP: `zaproxy/zap-stable:2.17.0@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af`,
    published 2026-11-03 (24 days old).

## Data — migration `0016_workspace` (`down_revision = "0015_team_lifecycle"`, full downgrade)

**Enums** are created complete up front (D38):
- `task_status` (TODO, IN_PROGRESS, REVIEW, DONE)
- `task_difficulty` (EASY, MEDIUM, HARD)
- `evidence_kind` (FILE, LINK, PR, SCREENSHOT)
- `comment_target` (TASK, MILESTONE, CHECKIN)
- `risk_type` (the nine §9.11 types)
- `risk_severity` (CRITICAL, MEDIUM, LOW)
- `risk_status` (OPEN, RESOLVED)
- `file_kind` gains `PROJECT_FILE` through `ALTER TYPE … ADD VALUE` in an `autocommit_block`.
  The downgrade rebuilds the type without it, after refusing if any project file exists.

| Table | Columns (all have `id uuid`, `created_at`; bounds as CHECKs) | Constraints / indexes |
|---|---|---|
| `tasks` | project_id, milestone_id, title 1–160, description ≤ 5000, assignee_id NULL → users, status, deadline date NULL, estimate_hours numeric(5,1) > 0 ≤ 999.9, difficulty, position text 1–64 (`[0-9A-Za-z]`), progress_pct smallint ∈ {0,50,85,100}, last_activity_at, created_by, version int | INDEX (milestone_id, status, position) §7.9; INDEX (project_id, assignee_id); progress_pct CHECK matches status |
| `task_dependencies` | project_id, task_id, depends_on_task_id | UNIQUE (task, depends_on); CHECK task ≠ depends_on; trigger: same milestone |
| `task_evidence` | project_id, task_id, kind, file_id NULL → files, url NULL ≤ 2048 `^https://`, note ≤ 500, added_by | CHECK kind ↔ (file_id XOR url); PR url pattern CHECK; immutable (`reject_mutation`) |
| `comments` | project_id, target_type, target_id, author_id, body 1–4000, mentions uuid[] ≤ 10, reply_to NULL → comments, edited_at, deleted_at, version | INDEX (target_type, target_id, created_at, id) |
| `comment_revisions` | comment_id, body, edited_at | written by trigger only (D169) |
| `discussion_threads` | project_id, title 3–120, created_by, last_post_at | INDEX (project_id, last_post_at DESC, id) |
| `discussion_posts` | project_id, thread_id, author_id, body 1–4000, mentions uuid[] ≤ 10, reply_to NULL, edited_at, deleted_at, version | INDEX (thread_id, created_at, id) |
| `discussion_post_revisions` | post_id, body, edited_at | as above |
| `checkins` | project_id, team_member_id, week_start date (a Monday, CHECK `extract(isodow)=1`), done 1–2000, next 1–2000, blockers ≤ 2000 NULL, confidence 1–5, on_time bool | UNIQUE (team_member_id, week_start); immutable (`reject_mutation`) |
| `activity_events` **AO** | project_id, actor_id NULL, subject_id NULL (D167), type text CHECK ∈ the 22 §9.1.6 types, entity_type, entity_id, data jsonb, at | INDEX (project_id, at) §7.9; INDEX (project_id, subject_id, type); `reject_mutation` on UPDATE/DELETE |
| `risks` | project_id, type, severity, entity_type, entity_id NULL, title ≤ 200, detail jsonb, status, opened_at, resolved_at, updated_at | INDEX (project_id, status, severity) §7.9; partial UNIQUE (project_id, type, entity_type, coalesce(entity_id, nil)) WHERE status='OPEN' |
| `forecast_snapshots` | project_id, day date, forecast jsonb, impact_days int, evaluated_at | UNIQUE (project_id, day) |
| `notification_preferences` | user_id, type text (a D162 category key), in_app bool, email bool, updated_at | UNIQUE (user_id, type) |
| `files` (changed) | + project_id NULL → projects | CHECK (kind = PROJECT_FILE) = (project_id IS NOT NULL); `files_identity_immutable()` also protects project_id; INDEX (project_id, created_at, id) WHERE deleted_at IS NULL |

**Helpers** (`STABLE`, `SET search_path = pg_catalog, public`, `REVOKE ALL FROM PUBLIC`, `GRANT
EXECUTE` to app and worker):
- `is_project_member(p)`: an ACTIVE member, or COMPLETED for reading.
- `is_active_project_member(p)`: ACTIVE only, used for writes.
- `is_participant(p)`: the client or `is_project_member`.
- `is_project_lead(p)`: the ACTIVE lead.
- `record_activity(p, type, entity_type, entity_id, subject, data) RETURNS uuid` (`SECURITY
  DEFINER`). It requires `app_uid()` NOT NULL, `is_participant(p)` and a type in the catalogue,
  and it sets `actor_id = app_uid()` itself (the actor is never a parameter). It refuses any other
  call with `insufficient_privilege`.
- `file_access()` is extended. A project file is readable by participants of its project while
  `deleted_at IS NULL`, and by the admin and SYSTEM; non-project files stay owner-only.

**Triggers:**
- `workspace_project_guard` (D166) and `task_dependency_same_milestone`.
- `comment_revision_capture` (D169).
- `reject_mutation` on `checkins`, `task_evidence` and `activity_events`.
- `tasks_version_bump`.

**Policies** (ENABLE + FORCE on every new table; `migrator_all`):

| Table | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| tasks, task_dependencies | participant, admin | active member | active member | active member (the service narrows to the lead) |
| task_evidence | participant, admin | active member, `added_by = app_uid()` | — | — |
| comments, discussion_posts | participant | participant, `author = app_uid()` | author | — (soft delete) |
| discussion_threads | participant | participant | creator | — |
| *_revisions | admin, SYSTEM | trigger (definer) | — | — |
| checkins | participant, admin | active member owning `team_member_id` | — | — |
| activity_events | participant, admin | SYSTEM (and the definer) | — | — |
| risks | client and admin: all; members: types other than BUDGET and AUTO_APPROVAL_SOON | SYSTEM | SYSTEM | — |
| forecast_snapshots | participant, admin | SYSTEM | SYSTEM | — |
| notification_preferences | own | own | own | own |
| files (extended) | `file_access(id)` | owner (as now) | owner or project lead (soft delete) | — |

**Settings v6:** `alembic/seed/platform_settings_v6.json` = v5 + `ratelimit.upload_bytes_per_day`
524 288 000 (schema: `int`, ge 1 MiB, le 10 GiB), inserted as version 6 by `0016` exactly as
`0011` inserted v5, and deleted by the downgrade. `PlatformSettings` gains a validator rejecting
`alerts.inactive_days ≥ alerts.repair_days` (D151).

**Housekeeping:**
- Every new table referencing `users` goes into `USER_SCOPED` in `test_demo_reset.py`.
- `check_rls.py` must report 0 unprotected tables.
- Run `make erd`.
- `purge_orphans` skips `kind = PROJECT_FILE` (D147).

## Notification catalogue (D162) — every kind mapped to a §12 row

| Category (pref key) | §12 row | Types | In-app / email default | Email can be switched |
|---|---|---|---|---|
| `bids_received` | New bid (batched) | NEW_BIDS | on / digest on | yes |
| `bidding_outcome` | Bidding deadline / too few bids | BIDDING_CLOSED, TOO_FEW_BIDS, TOO_FEW_BIDS_REMINDER, PROJECT_CANCELLED | on / on | yes |
| `formation` | Team formation finished | FORMATION_FINISHED, REPAIR_READY | on / — | in-app only |
| `selected` | Selected / replacement invitation | INVITATION_SELECTED | on / on | yes |
| `bid_updates` | Not selected (+ other changes to your bid) | BID_NOT_SELECTED, BID_INELIGIBLE, PROJECT_TERMS_CHANGED, BIDDING_REOPENED, SLOT_CLOSED | on / — | in-app only |
| `invitation_responses` | Invitation accepted/declined/expired | INVITATION_ACCEPTED, INVITATION_DECLINED, INVITATION_EXPIRED | on / — | in-app only |
| `team` | Project started / lead / lead changed | PROJECT_STARTED, LEAD_CHOSEN, LEAD_CHANGED, LEAD_DECLINED, LEAD_CHANGE_REQUESTED, LEAD_CHANGE_DECIDED, MEMBER_LEFT, MEMBER_REMOVED, REMOVAL_DECIDED | on / on | yes |
| `task_assigned` | Task assigned | TASK_ASSIGNED, TASKS_UNASSIGNED (to the lead) | on / — | in-app only |
| `mentions` | Mentioned in comment | MENTIONED | on / **off** (opt-in, D153) | yes |
| `blockers` | Blocker reported | BLOCKER_REPORTED | on / — | in-app only |
| `checkin_reminder` | Check-in reminder | CHECKIN_REMINDER | on / on | yes |
| `critical_risk` | Risk opened (CRITICAL) | RISK_CRITICAL | on / on | yes |
| `verification` | Certificate verified/rejected | ROLE_ASSESSMENT_VOIDED | on / — | in-app only |

Account and security emails (the six `ACCOUNT_TEMPLATES`) aren't in the table: they can't be
switched off and aren't shown. `PROJECT_CANCELLED` for bidders (projects.py) and for the auto-close
(bidding_jobs) are the same type, so one switch covers both.

New email templates in `integrations/email.py` (autoescaped, nothing private about others):
`mentioned`, `checkin_reminder` and `risk_critical`. They're checked in Mailpit.

## Evidence events (D149) — which event carries which §9.1.4–9.1.5 input

| Input | Events and `data` |
|---|---|
| Check-in on-time ratio (on-time / expected) | `checkin.posted {week_start, on_time}` + `checkin.missed {week_start}` (subject = member); expected = posted + missed |
| Reply score (median reply time to comments that mention them) | `comment.posted {target_type, target_id, mentions[]}` + `comment.replied {reply_to_id, to_author_id, response_seconds}`, from both comments and `DISCUSSION_POST` |
| Claims match (DONE not reopened) | `task.done {task_id, milestone_id, assignee_id, estimate_hours}` and `task.reopened {task_id, from: DONE}` |
| Work started on or before the promised date | `work.started {task_id}` (the member's first move to IN_PROGRESS on the project); the promised date comes from the bid |
| Help (blockers answered) | `blocker.reported {checkin_id}` + `blocker.answered {checkin_id, comment_id}` (actor = the helper; first reply by another member only) |
| §9.13 completed hours per milestone | `task.done` / `task.reopened` (estimate, milestone, assignee at that moment) |
| Moves and evidence (Evidence tab) | `task.moved {task_id, milestone_id, from, to, assignee_id, estimate_hours}`, `task.evidence_added {task_id, kind}` |
| Team changes | `member.left {slot_label, how: LEFT/REMOVED}`, `member.replaced {slot_label}` (no reasons, D149) |

Schemas for all 22 types live in `app/schemas/activity.py`. The ones Phases 10–13 emit are written
and tested now. `data` never carries money, days or reasons. A test scans the feed as a member.

## Backend — algorithms (PURE, ≥ 95 % coverage)

- **`algorithms/positions.py`** — `key_between(a, b)`: base-62 midpoint keys, plus
  `needs_rekey(key)` (length > 48) and `spread(n)` for re-keying. Property tests:
  - `a < key_between(a, b) < b`;
  - keys stay ≤ 12 characters after 1,000 appends or prepends;
  - re-keying preserves the order.
- **`algorithms/forecast.py` (D161)** — exact `Fraction` arithmetic with `milestone_progress_exact`.
  The §18.2 test gives finish 25 and impact +2, and boundary tests cover progress values where the
  float version adds a day.
- **`algorithms/risks.py`** — `evaluate(inputs, settings) → Evaluation`. There's one function per
  §9.11 rule, plus `team_health`, `overall_risk`, `schedule_progress`, `budget_usage`,
  `milestone_state` (the D151 mapping) and `project_day` (Asia/Dhaka). Inputs are frozen
  dataclasses (milestones with baseline and forecast, tasks, members with last activity and hours,
  money figures that are zero until Phase 10), so the engine needs no DB or clock. CRITICAL_PATH_DELAY
  and SLACK_EATEN look only at ACTIVE milestones. The engine also produces the snapshot's delay
  causes.

## Backend — services, jobs, routes

- **`services/workspace.py`** — `load_participant(ctx, project_id, *, write)`:
  - It returns the project, the caller's member row and the role (CLIENT / MEMBER / LEAD / ADMIN).
  - Anyone else gets 404, including INVITED, DECLINED, EXPIRED, LEFT and REMOVED members (D142).
  - `write=True` requires `IN_PROGRESS` (409 `INVALID_STATE` with `allowed_actions`); admins get
    403 on any write.
  - Every workspace service uses it.
- **`services/tasks.py`**:
  - **CRUD:** create, patch (lead), delete (lead, not DONE). The milestone can be any unfinished
    one. Caps (D63) are named constants checked under a per-project advisory lock: 1,000 tasks per
    project, 20 dependencies per task, 20 evidence items per task.
  - **Moves:** one step at a time. A task can leave TODO only in ACTIVE or CHANGES_REQUESTED
    milestones. DONE needs every dependency DONE; leaving DONE is blocked while a dependent is
    DONE. Both 409s name the tasks. The assignee or the lead may move a task (only the lead for an
    unassigned one). Each move checks `If-Match` and takes the per-milestone advisory lock for the
    new position key (D144).
  - **Dependencies:** acyclic, so a cycle gets 409 with the path.
  - **Evidence (D148, D168).**
  - **Effects of each change:**
    - audit entries for creation, every status move, reassignment and deletion;
    - activity events through `record_activity`;
    - the `last_activity_at` bump;
    - the `TASK_ASSIGNED` notification;
    - `mon:dirty` and the dashboard cache bump after commit.
  - **Lock order:** project → milestone → task → dependents.
- **`services/checkins.py`**:
  - **Week and on-time:** the week is computed in Asia/Dhaka from `ctx.now`; on time means up to
    Tuesday 23:59:59.999999 Dhaka.
  - **Posting:** a duplicate gets 409 `CHECKIN_EXISTS` (also when two arrive at once, via the
    UNIQUE index).
  - **Blockers:** non-empty blockers raise `BLOCKER_REPORTED` to the lead.
  - **Feed:** cursor by (week_start desc, member order); it includes this week's due time and the
    members still missing.
  - **Expected weeks:** `expected_weeks(member)` follows D145.
- **`services/comments.py`** (and `services/discussion.py`):
  - **Targets:** the target must belong to the project, including a check-in's project.
  - **Mentions:** the server keeps only the project's participants, dedupes, and allows ≤ 10
    (422 above 10). Mentioned users get `MENTIONED` (in-app; email per preference).
  - **Replies:** `reply_to` must be on the same target. `comment.replied` fires when the replied-to
    author had mentioned the replier. `blocker.answered` fires on the first reply to a check-in by
    another member.
  - **Editing and deleting:** edits are allowed ≤ 15 min after posting (409
    `EDIT_WINDOW_CLOSED`); soft delete hides the body.
  - **Limits:** comments and posts share the `ratelimit.comment` bucket.
  - **Discussion:** threads plus posts with the same rules; posts update `last_post_at`.
- **`services/project_files.py`**:
  - **Upload:** through the existing `uploads/pipeline.py`, with `FileKind.PROJECT_FILE` allowing
    exactly §14.9's types (images re-encoded, PDF ≤ 10 MB, text/markdown ≤ 1 MB).
  - **Limits:** `ratelimit.upload` (20/h), plus the daily byte budget, a Redis counter
    `upload:bytes:{user}:{dhaka-date}` with a 24 h TTL. It's checked before streaming (using
    Content-Length) and charged with the stored size. Over budget gets 429 with `Retry-After` until
    Dhaka midnight. Redis down → fail closed (503), as the upload scope already does.
  - **List and delete:** the list shows the linked task and milestone from evidence. Soft delete
    by the uploader or the lead.
  - **Download:** the existing `GET /files/{id}/download` keeps the signed-URL path.
- **`services/activity.py`** — `record()` uses the definer for user requests and inserts directly
  on SYSTEM paths. Payloads are validated by `schemas/activity.py`. The Phase 8 hooks go into
  `team._depart` (`member.left`) and accept-as-replacement (`member.replaced`).
- **`services/monitoring.py`**:
  - **`evaluate(project_id, now)`:**
    - It takes a SYSTEM session and a per-project advisory lock (so evaluation can't race itself),
      loads the inputs and runs `risks.evaluate`.
    - It upserts the risks: opening, escalating and resolving them.
    - It upserts today's snapshot, with each milestone's planned and forecast start and finish,
      the finish, the impact and the causes.
    - `RISK_CRITICAL` goes to the client and the lead only when a risk opens as CRITICAL or is
      raised to it.
    - It bumps the cache.
  - **Reads:** `dashboard(ctx, id)` (role-shaped `DashboardForClient` / `DashboardForMember`),
    `risks` (role-filtered, with the RLS row filter as well), `activity` (cursor) and
    `evidence_summary`.
  - **Inactivity:** `member_inactive_days` gets its D150 body. `team.request_removal` uses it at
    ≥ `alerts.repair_days`.
- **`services/projects.get_plan`:**
  - **Readers:** participants can now read it (D142). Client-only paths keep `_load_for_read`.
  - **Forecast:** when `IN_PROGRESS`, it adds `forecast` (per node: forecast ES and EF, status,
    progress 0–100, revision count, actual dates; plus finish, impact and critical paths) from the
    latest snapshot (D152).
- **`services/notifications.py`:**
  - async `notify` with preferences and after-commit publish (D162–D164);
  - `stream_since(user, last_id)`;
  - `preferences` get/put (own rows; defaults are filled in on read, not stored).
- **`core/cache.py`** — `cached(key_parts, ttl, loader)`:
  - Key: `cache:v1:{name}:{gen}:{parts}`, where `gen` is `INCR cache:gen:{scope}`, bumped after
    commit (invalidation = a new generation, so stale entries just expire).
  - Single-flight: `SET lock NX PX 5000`; others poll up to 2 s, then load themselves.
  - JSON values through Pydantic.
  - Redis down → load directly (cache is optional, never a security gate).
  - The dashboard key includes the **shape** (client/member/admin), so two shapes never share an
    entry.
- **Jobs:**
  - `core/task_queue.TASKS` gains `monitoring.evaluate` (default queue, 60 s, 1 retry) and
    `checkin.reminders` (default, 300 s, 1 retry).
  - `jobs/monitoring_jobs.py` holds the two jobs plus `monitoring.flush` and `monitoring.sweep`
    (which only enqueue).
  - `jobs/scheduler.py` gains:
    - `monitoring.sweep`: every 15 min;
    - `monitoring.flush`: every 30 s;
    - `checkin.reminders`: cron Monday 10:00, `timezone=Asia/Dhaka`.
  - Each job re-loads and re-checks its entities. Reminders and missed weeks are idempotent per
    member-week (`notify_once` with `since=week_start`, and an existence check before
    `checkin.missed`).
- **The stream** (`api/v1/notifications.py`), D107 exactly:
  - It uses `acquire_stream` / `release_stream`, the same `sse:concurrent:{user}` counter as jobs
    (3 in all).
  - On connect it runs one short query for notifications newer than `Last-Event-ID` (≤ 50) and
    releases the session, then subscribes to `notif:{user}`.
  - Heartbeat every 20 s; it closes at `SSE_MAX_SECONDS` (30 min, configurable for the test).
  - Events: `id`, `event: notification`, `data {id, type, title}`.
- **Nginx:** a location `= /api/v1/notifications/stream` including `proxy-sse.conf` (no
  buffering), with an edge test.
- **Authz:** `core/authz.py` gets one policy per action, scoped per project (lead powers only in
  their project), and every route goes into the matrix test.

## Endpoint table (contract-first; `StrictRequest` bodies; all errors `ErrorResponse`)

Common errors on every row: **401** `UNAUTHENTICATED`, **404** `NOT_FOUND` (project, task or row
not visible: non-participant, former member, other project), **422** `VALIDATION_ERROR` (including
unknown query params → **400** `BAD_REQUEST` per §10.1, limit > 100), **429** `RATE_LIMITED` where
a limit applies. Writes add **403** `ROLE_NOT_ALLOWED` (a client on a task action, a member on a
lead action, an admin on any write) and **409** `INVALID_STATE` (project not IN_PROGRESS, with
`current_state` and `allowed_actions`). `If-Match` routes add **409** `VERSION_CONFLICT` (D66). On task routes the
header is **required**: a missing one is 422 with `fields.If-Match`, because a move without a
version could silently overwrite another drop. That's stricter than bids, where it's optional.

New `ErrorCode`s: `DEPENDENCIES_NOT_DONE`, `DEPENDENTS_DONE`, `ONE_STEP_ONLY`,
`MILESTONE_NOT_ACTIVE`, `MILESTONE_FINISHED`, `DEPENDENCY_CYCLE`, `DEPENDENCIES_BLOCK_MOVE`,
`CHECKIN_EXISTS`, `EDIT_WINDOW_CLOSED`. The caps use the existing `LIMIT_REACHED`; the stream uses
the existing `RATE_LIMITED` and `CSRF_FAILED`, like the jobs stream.

| # | Method & path | Who | Request → response | Specific errors | Example |
|---|---|---|---|---|---|
| 1 | GET `/milestones/{id}/tasks?status=&assignee_id=&cursor=&limit=` | participant, admin | → `Page[TaskCard]` ordered (status, position, id) | — | `{"items":[{"id":"…","title":"Stock list API","status":"IN_PROGRESS","assignee":{"id":"…","name":"Nusrat"},"deadline":"2026-11-20","estimate_hours":"8.0","difficulty":"MEDIUM","position":"V","progress_pct":50,"blocked_by":0,"evidence_count":1,"comment_count":2,"version":3}],"next_cursor":null}` |
| 2 | POST `/milestones/{id}/tasks` | lead | `TaskCreate {title, description?, assignee_id?, deadline?, estimate_hours, difficulty, depends_on_ids? ≤ 20}` → 201 `TaskDetail` | 409 `MILESTONE_FINISHED`, `LIMIT_REACHED`, `DEPENDENCY_CYCLE`; 422 assignee not an ACTIVE member, deadline before start | `{"title":"Stock list API","estimate_hours":"8.0","difficulty":"MEDIUM","assignee_id":"…"}` → 201 `{…,"status":"TODO","version":1}` |
| 3 | GET `/projects/{id}/tasks?milestone_id=&assignee_id=&mine=&status=&cursor=&limit=` | participant, admin | → `Page[TaskCard]` (50 per column page, D158) | — | as #1 |
| 4 | GET `/tasks/{id}` | participant, admin | → `TaskDetail` (+ dependencies, dependents, evidence, counts, `can_move_to[]` with reasons for the caller) | — | `{"id":"…","status":"TODO","can_move_to":[{"status":"IN_PROGRESS","allowed":false,"reason":"Its milestone hasn’t started yet."}],…}` |
| 5 | PATCH `/tasks/{id}` (If-Match) | lead | `TaskPatch {title?, description?, assignee_id?, deadline?, estimate_hours?, difficulty?, milestone_id?}` → `TaskDetail` | 409 `DEPENDENCIES_BLOCK_MOVE` (milestone change), `MILESTONE_FINISHED`, `INVALID_STATE` (milestone change when not TODO) | `{"assignee_id":null}` → 200 `{…,"assignee":null,"version":4}` |
| 6 | POST `/tasks/{id}/move` (If-Match) | assignee, lead | `TaskMove {status, after_id?, before_id?}` → `TaskCard` | 409 `ONE_STEP_ONLY`, `MILESTONE_NOT_ACTIVE`, `DEPENDENCIES_NOT_DONE` / `DEPENDENTS_DONE` (with `fields.tasks`); 422 neighbours not in that column; 403 another member / client | `{"status":"REVIEW","after_id":"…"}` → 200 `{…,"status":"REVIEW","progress_pct":85,"position":"Vk","version":5}` |
| 7 | DELETE `/tasks/{id}` (If-Match) | lead | → 204 | 409 `INVALID_STATE` (DONE) | — |
| 8 | POST `/tasks/{id}/dependencies` | lead | `{depends_on_task_id}` → 201 `TaskDependency` | 409 `DEPENDENCY_CYCLE` (`fields.cycle` = titles in order), `LIMIT_REACHED`; 422 other milestone or itself | `{"depends_on_task_id":"…"}` → `{"task_id":"…","depends_on_task_id":"…"}` |
| 9 | DELETE `/tasks/{id}/dependencies/{depends_on_task_id}` | lead | → 204 | — | — |
| 10 | POST `/tasks/{id}/evidence` | assignee, lead | `EvidenceCreate {kind, url?, file_id?, note?}` → 201 `Evidence` | 409 `LIMIT_REACHED`; 422 non-https, bad PR format, foreign or deleted or non-image file | `{"kind":"PR","url":"https://github.com/acme/inv/pull/12"}` |
| 11 | GET `/comments?target_type=&target_id=&cursor=&limit=` | participant | → `Page[Comment]` (created_at, id) | — | `{"items":[{"id":"…","author":{"id":"…","name":"Arif"},"body":"@Nusrat can you check?","mentions":[…],"edited":false,"deleted":false,"reply_to_id":null,"version":1}]}` |
| 12 | POST `/comments` | participant (admin 403) | `CommentCreate {target_type, target_id, body ≤ 4000, mention_ids ≤ 10, reply_to_id?}` → 201 `Comment` | 422 reply on another target | `{"target_type":"TASK","target_id":"…","body":"Looks good","mention_ids":[]}` |
| 13 | PATCH `/comments/{id}` (If-Match) · DELETE `/comments/{id}` | author | `{body}` → `Comment` · 204 | 409 `EDIT_WINDOW_CLOSED`; 403 not the author | `{"body":"Looks good now"}` → `{…,"edited":true}` |
| 14 | GET `/projects/{id}/checkins?member_id=&cursor=&limit=` | participant, admin | → `CheckinFeed {items: Checkin[], next_cursor, this_week {week_start, due_at, missing_member_ids[]}}` | — | `{"items":[{"id":"…","member":{…},"week_start":"2026-11-23","done":"…","next":"…","blockers":null,"confidence":4,"on_time":true,"reply_count":0}],"next_cursor":null,"this_week":{…}}` |
| 15 | POST `/projects/{id}/checkins` | active member | `CheckinCreate {done, next, blockers?, confidence}` → 201 `Checkin` | 409 `CHECKIN_EXISTS` | `{"done":"Finished the stock table","next":"Filters","confidence":4}` |
| 16 | GET `/projects/{id}/threads?cursor=&limit=` · POST | participant (admin 403 on POST) | `ThreadCreate {title 3–120, body, mention_ids}` → 201 `Thread` (+ first post) | — | `{"title":"Release checklist","body":"Draft below","mention_ids":[]}` |
| 17 | GET `/threads/{id}/posts?cursor=&limit=` · POST | participant | `PostCreate {body, mention_ids, reply_to_id?}` → 201 `Post` | as #12 | `{"body":"Agreed","mention_ids":[]}` |
| 18 | PATCH `/posts/{id}` (If-Match) · DELETE `/posts/{id}` | author | as #13 | as #13 | — |
| 19 | POST `/projects/{id}/files` (multipart `file`) | participant (admin 403) | → 201 `ProjectFile {id, name, mime, size_bytes, uploaded_by, created_at, links[]}` | 413, 415 by signature, 429 (20/h or bytes/day) | — |
| 20 | GET `/projects/{id}/files?cursor=&limit=` | participant | → `Page[ProjectFile]` (created_at desc, id) | — | `{"items":[{"id":"…","name":"wireframes.pdf","mime":"application/pdf","size_bytes":204800,"links":[{"task_id":"…","task_title":"UI kit","milestone_title":"UI design"}]}]}` |
| 21 | DELETE `/files/{id}` | uploader, lead (project files only) | → 204 | 403 other member | — |
| 22 | GET `/projects/{id}/dashboard` | participant, admin | → `DashboardForClient` (client/admin: + `budget {released_paisa, committed_paisa, remaining_paisa}`) or `DashboardForMember` | 409 `INVALID_STATE` before start | `{"progress_pct":41,"schedule":{"actual":0.41,"planned":0.48},"forecast":{"finish_day":25,"impact_days":2,"finish_date":"…"},"health":"AT_RISK","overall_risk":"CRITICAL","top_risks":[…],"next_milestone":{…},"evaluated_at":"…"}` |
| 23 | GET `/projects/{id}/risks?status=OPEN&severity=` | participant, admin | → `RiskList {items: Risk[]}` (severity, opened_at, id; role-filtered) | — | `{"items":[{"type":"CRITICAL_PATH_DELAY","severity":"CRITICAL","title":"Dashboard frontend late pushes deadline by 2 days","why":"…","actions":["REPLAN"],…}]}` |
| 24 | GET `/projects/{id}/activity?type=&actor_id=&cursor=&limit=` | participant, admin | → `Page[ActivityItem]` (at desc, id) | — | `{"items":[{"type":"task.done","actor":{…},"summary":"Nusrat moved “Stock list API” to Done","at":"…"}]}` |
| 25 | GET `/projects/{id}/evidence` | participant, admin | → `EvidenceSummary {members: [{member, checkins_on_time, checkins_expected, tasks_done, hours_done, comments, replies, blockers_answered, last_active_at}]}` (role, then name, D140) | — | — |
| 26 | GET `/projects/{id}/plan` (extended) | client, participant, admin | → `ProjectPlan` + `forecast: PlanForecast \| null` | — | `{"forecast":{"finish_day":25,"impact_days":2,"nodes":[{"milestone_id":"…","status":"ACTIVE","progress_pct":40,"forecast_es":8,"forecast_ef":18,"revision_count":0}],"critical_paths":[…]}}` |
| 27 | GET `/notifications/stream` (SSE) | session | → `text/event-stream` | 403 `CSRF_FAILED` (bad Origin / Sec-Fetch-Site); 429 `RATE_LIMITED` (4th stream, jobs included) | `id: <uuid>\nevent: notification\ndata: {"id":"…","type":"MENTIONED","title":"Arif mentioned you"}` |
| 28 | GET `/notification-preferences` · PUT | session | → `Preferences {items: [{category, label, in_app, email, email_available}]}`; PUT `{items: [{category, in_app, email}]}` | 422 unknown category, email on an in-app-only row | — |
| 29 | GET `/me/projects?state=active\|completed&cursor=&limit=` | developer | → `Page[MyProject] {project, role, is_lead, progress_pct, next_deadline, overall_risk}` | 403 client | — |
| 30 | test-only POST `/__test__/projects/{id}/monitoring/evaluate {as_of?}` · POST `/__test__/checkin-reminders {as_of?}` | `DEVSYNC_ENV=test` | → evaluation summary · `{reminded, missed}` | — | (D155; no stored timestamp changes) |

`GET /files/{id}/download` is unchanged in shape, extended in who may call it (`file_access`).

## OpenAPI change note (§10.4)

`docs/api/openapi.json` changes in Phase 9:
- **New:** operations 1–29 above; schemas `TaskCard`, `TaskDetail`, `TaskCreate`, `TaskPatch`,
  `TaskMove`, `TaskDependency`, `Evidence(Create)`, `Comment(Create/Patch)`, `Checkin(Create)`,
  `CheckinFeed`, `Thread(Create)`, `Post(Create/Patch)`, `ProjectFile`, `DashboardForClient`,
  `DashboardForMember`, `Risk`, `RiskList`, `ActivityItem`, `EvidenceSummary`, `PlanForecast`,
  `Preferences`, `PreferencesUpdate`, `MyProject`; new `ErrorCode` values.
- **Changed:** `ProjectPlan` gains `forecast` (nullable, additive). `GET /projects/{id}/plan` now
  also answers participants. `GET /notifications` items carry `type` from the catalogue (same
  field, now an enum).
- **Removed:** nothing.
- `make openapi` and `npm run api:types` run after each API change.

## Security — §14.13 row 9 and how each control is tested

| Control | Mechanism | Test |
|---|---|---|
| RLS on workspace tables | ENABLE + FORCE, the policies above, D166 guard | `tests/security/test_rls_workspace.py`: each table as client, member, other project's member, former member, admin and SYSTEM; `check_rls.py` 0 unprotected |
| Comment/discussion text | plain text only; React renders text; `linkify()` only `https://` with `rel="noopener noreferrer nofollow"` | injection corpus stored and returned byte-identical and inert (API); Vitest linkifier (`javascript:`, `data:`, `http:`, mixed case, encoded) |
| Mention validation | server keeps participants only, ≤ 10 | non-member dropped (no row, no notification); 11 → 422 |
| File authz in workspace | `file_access()` + `load_participant` + soft delete | other project's participant, former member, other client → 404; delete rules; deleted file never served; the §16.4 upload list for `PROJECT_FILE`; byte budget boundary |
| SSE auth, Origin, limits | D107 path + shared counter | no session 401; foreign Origin and `Sec-Fetch-Site: cross-site` 403; 3 job+notification streams then 429; heartbeat; close with a short `SSE_MAX_SECONDS`; `Last-Event-ID` resume; only own events; Nginx edge test |
| Activity append-only | `reject_mutation`; SYSTEM or definer inserts | UPDATE/DELETE fail as every role; definer refuses other actor, non-participant, unknown type |
| Role-shaped money | separate response models; risk RLS filter; cache key per shape | scan a member's dashboard, risks, plan and activity responses for `_paisa`, BUDGET, AUTO_APPROVAL_SOON; cache shape test |
| Mass assignment | `StrictRequest` | `author_id`, `actor_id`, `position`, `progress_pct`, `on_time`, `status` on create, `project_id`, `deleted_at`, `week_start` → 422 |
| GET never mutates | — | DB checksum around every new GET (dashboard and stream included) |
| Per-project lead powers | `authz` policies take the project | lead of project A on project B's tasks → 404/403 |

## Tests by layer (never happy-path-only; FR-MON-1…10 and FR-PROJ-6 in names)

- **unit / property (algorithms):**
  - each §9.11 rule firing and resolving at its boundary, per severity step, including D151's
    started-only rule and the state mapping;
  - team health thresholds, overall risk, schedule progress, budget usage;
  - progress weights;
  - forecast on §18.2 (25, +2) and D161 boundaries;
  - position keys (property);
  - `linkify`;
  - Dhaka week and on-time at Tuesday 23:59 ±1 min (`FrozenClock`);
  - expected weeks;
  - event schemas (good and bad payload for all 22);
  - the notification catalogue covers every caller (grep test) and every template.
- **integration:**
  - task dependency rules (DONE blocked; leaving DONE blocked by a DONE dependent; same milestone;
    cycle path; cap 20);
  - one-step moves;
  - ACTIVE/CHANGES_REQUESTED only;
  - stale `If-Match`;
  - progress and forecast after moves;
  - a leaving member's tasks unassigned and the lead notified;
  - check-ins (duplicate 409, concurrent double post → one row);
  - comments (edit 15 min boundary, revisions kept, soft delete, reply rules, shared 60/h at
    59/60/61, 4000/4001);
  - files and limits;
  - Phase 8 hooks fire;
  - `member_inactive_days` and removal at 9/10 days;
  - preference off → no Phase 8 notification and no email;
  - publish-after-commit (rollback publishes nothing);
  - `USER_SCOPED` reset.
- **api:**
  - every route's status codes and examples;
  - move permissions (assignee vs lead vs other member vs client 403);
  - unknown params 400, limit > 100;
  - array caps 422;
  - schemathesis plus the stateful `TaskLifecycle` machine (create → assign → move through columns
    → evidence → comment → delete) next to `BidLifecycle`.
- **security:** the table above; authz matrix rows for every new route × anonymous, client, other
  client, member, lead, other project's lead, former member, admin; IDOR on every id (task,
  dependency, evidence, comment, thread, post, check-in, file, risk).
- **jobs** (`SimpleWorker`):
  - `monitoring.evaluate`:
    - idempotent;
    - upsert, escalation and resolution;
    - CRITICAL notification once per opening;
    - safe to retry;
    - 60 s timeout.
  - `checkin.reminders`:
    - reminds only members who haven't posted;
    - missed weeks recorded once, with a catch-up after a skipped run;
    - 300 s timeout.
  - **Debounce:** a burst followed by a late event leads to a final evaluation that sees the last
    event (D165).
  - **Concurrency:** evaluation racing a task move leaves one consistent state.
- **perf** (`perf` marker): evaluate on 50 milestones / 500 tasks inside 60 s, with a target of
  < 5 s; dashboard < 2 s.
- **Query counts** (dashboard, task list, check-in feed): fixed maxima.
- **fuzz:** `make fuzz` on the new endpoints.
- **frontend (Vitest, a file per module):**
  - `KanbanBoard` (columns, refused target reason, optimistic move and rollback, client has no
    handles, keyboard sensor announcements, Move to… menu, Show more);
  - task drawer, NewTaskForm schema;
  - `RiskList`, `BudgetDonut`, `HealthBadge`, the forecast Gantt layers, `CpmList`;
  - check-in form schema and feed, comments and mentions picker, linkifier, discussion polling;
  - files list, Evidence summary, Overview, Milestones tab;
  - `useNotificationStream` (reconnect with backoff, fallback poll);
  - preferences form, My projects, dashboard parts;
  - the workspace tab bar (D160: eleven tabs, Payments placeholder only).
- **E2E** (`frontend/e2e/phase9.spec.ts`, Chromium, `@e2e`), the §17 flow:
  - lead creates tasks;
  - members move tasks with mouse **and** keyboard;
  - check-ins, a comment with a mention, an upload;
  - the client opens Overview, Timeline, Risks, Milestones and Check-ins, with no handles or task
    actions, and an API move returns 403;
  - `as_of` makes a late critical milestone produce a CRITICAL risk with the impact;
  - on the 390×844 touch profile: a long-press move and a Move to… move, with column tabs and snap;
  - the mentioned member's bell updates live.

  Also run once on Firefox and WebKit before the push.
- **a11y / visual / CSP:**
  - every new screen is registered in `screens.ts` or `stateful-screens.ts`, with a
    `startedProject()` helper factored out of the `workspace-team` setup;
  - volatile text is masked (`[data-volatile]`: relative times, dates, the today line);
  - `csp.spec.ts` covers a Kanban drag and a virtualized long list;
  - the keyboard-only walkthrough is written into `docs/TESTING.md` (§22).
- **Coverage:** backend ≥ 85 %, frontend ≥ 70 %, `app/algorithms/` ≥ 95 %, and ≥ 95 % for the
  critical modules (`uploads/*`, `core/ratelimit.py`, `core/redirects.py`, `core/authz.py`).

## Frontend (devsync-ui + frontend-design; four states; light/dark; 375–1440; reduced motion)

The workspace becomes a layout route `/w/:projectId` with nested lazy routes. The default is
`overview`; a `TEAM_PENDING` project still shows only Team. The §13.4 tab bar uses real links and
keeps Phase 8's phone scroller fix. It's role-aware: the client sees no task actions, drag handles,
check-in form or evidence buttons; the lead's tools appear in place ("New task", assign, delete).

| Screen | Content | Phone layout |
|---|---|---|
| Overview (29) | `RingProgress` progress; schedule planned vs actual bar; `BudgetDonut` (client: released 0 / committed 0 honestly until Phase 10); forecast finish + impact chip; health badge; overall risk; top 3 risks with actions; next milestone; recent activity; "Updated N minutes ago" (volatile) | single column, stat cards 2×2, donut with table toggle |
| Tasks (30) | `KanbanBoard` (dnd-kit pointer + keyboard + touch sensors with announcements); filters milestone / assignee / only mine; cards per §13.5; refused drop says why; Move to… on every card; drawer (details, dependencies, evidence, files, comments + mentions, activity); lead's New task | one column per screen, snap scroll, column tabs, 300 ms long-press, edge auto-scroll, FAB "New task" for the lead; drawer → full-screen sheet |
| Timeline (31) | `Gantt` extended with baseline vs forecast bars, critical path, today line, milestone panel on click; "View as table" | defaults to `CpmList` cards (dates, slack, critical badge) with "Show timeline" (sticky names, zoom buttons). Shared with the plan page |
| Milestones (32, read-only) | per milestone: status, share, planned and forecast dates, progress from tasks, revision count; "Submission and payment arrive in Phase 10" | card list |
| Team (33) | + "contribution so far" (tasks done, hours done) | card list |
| Check-ins (34) | weekly form (done, next, blockers, confidence slider 1–5) for members; feed by week (virtualized > 50); missing check-in warnings; blocker replies | form first, feed below; replies as full-screen thread |
| Files (35) | `FileDropzone`; list (name, uploader, size, linked task/milestone, download, delete) | card list, upload button full width |
| Discussion (36) | threads, posts, mentions, 15-minute edit with "edited", 15 s polling while visible | thread full-screen with the input fixed above the keyboard |
| Evidence (38) | per-member activity summary; the GitHub part says "GitHub evidence arrives in Phase 13"; spec note on what reputation uses | stacked member cards |
| Risks (39) | `RiskList` grouped CRITICAL/MEDIUM/LOW: title, one-sentence why, actions (Find replacement → Phase 8 removal/repair; Re-plan → Timeline; Message member → Discussion) | full-width cards |
| Payments | "Payments arrive in Phase 10" | — |
| My projects (13) `/dev/projects` | Active / Completed tabs; nav marker dropped | card list |
| Dashboards (9, 20) | developer: progress ring, next deadline, risk chip per active project; client: progress, impact chip, risk chips on dashboard and `/client/projects`; client "Recent activity" includes workspace events | stacked |
| Plan page (22) | baseline/forecast toggle with the shared Gantt/CpmList | as Timeline |
| Notifications (18) | live via `useNotificationStream`; 60 s refresh kept as fallback; link to preferences | virtualized list |
| Settings (19) | notification preferences per §12 row; account emails listed as always on | switches stacked |

Rules applied everywhere:
- Every list is in a total order (D140).
- Data comes only from `features/*/api.ts` hooks: lists use `staleTime` 30 s, dashboards refetch
  on focus.
- Task moves, comments and notification reads are optimistic, with rollback.
- Custom SVG charts only (D95), each with "View as table".
- Tokens and `motion.ts` only.
- Each route chunk stays ≤ 150 KB gzip.
- Every workspace notification links to the exact tab or task (`/w/:id/tasks?task=…`).

## Seed and gate

- **The Inventory dashboard seed (D154, D170):**
  - `seed_demo.py --day N` (default 12) builds the project through the real services: publish,
    bids, `formation_runner`, confirm, accept, lead, start. The clock is frozen at past days so the
    start date is today − N.
  - Then one commented SYSTEM helper makes Phase 10's milestone transitions (Requirements APPROVED
    day 3; UI design ACTIVE day 3 → APPROVED day 8 with `revision_count = 1`; Inventory API ACTIVE
    from day 4; Dashboard frontend ACTIVE from day 8).
  - Tasks, moves, check-ins and comments go through the Phase 9 services under a `FrozenClock` per
    simulated project day ≤ min(12, N).
  - Estimates are chosen for p = 0.7 and p = 0.4 exactly (for example 10 h tasks: API 7/10 done,
    frontend 4/10 done-equivalent).
  - The inactive member is chosen so that SKILL_DEPENDENCY, STALLED_TASK and CAPACITY don't fire.
  - The script asserts the end state at DAY = 12: forecast 25, +2, exactly {CRITICAL_PATH_DELAY
    (Dashboard frontend), SLACK_EATEN (Inventory API), DEADLINE_IMPACT MEDIUM, INACTIVE_MEMBER
    MEDIUM}, health At risk, overall CRITICAL.
  - Its people and dates don't overlap the ordering project; the D116 team, golden reputations and
    Clinic repair are re-asserted.
  - The Makefile passes `DAY` to `seed-demo`, `demo-reset` and `demo-up`.
  - `demo-reset STAGE=2` is measured and must stay < 30 s.
  - The stage-2 accounts header bug ("STAGE 1") is fixed in passing.
- **`phase9_checks`:**
  - `phase8_checks` first (which chains 7 and 6);
  - then `scripts/monitoring_check.py` (like `repair_check.py`), which asserts the seeded risks and
    impact;
  - then the named Phase 9 security and RLS tests.
- **DAST (D157, D171):**
  - `step_dast` and `make zap` run `zap-baseline.py` against the running test stack through Nginx
    over HTTPS.
  - **Authentication:** a seeded test user's session cookie, obtained from the test router and
    passed as a header through ZAP's replacer options.
  - **Spider:** sign-out and every state-changing URL are excluded; the start URLs are the main
    signed-in pages and a workspace.
  - **TLS:** the self-signed certificate is accepted for this target only.
  - **Output:** reports go to `runs/zap/`.
  - **Pass rule:** it fails on any High or Medium. Ignore rules are only allowed with a DECISIONS
    entry naming the alert.
  - **Offline:** `--offline` records a skip.
  - **Pre-pull note:** Known issues gets the image and digest Taeen should pull before the gate.
  - **Trial run on day 1.**

## Files, in the D159 build order

0. `DECISIONS.md` D162–D171; this plan.
1. **Migration and RLS:**
   - `alembic/versions/0016_workspace.py`, `alembic/seed/platform_settings_v6.json`;
   - `models/workspace.py`, `models/profiles.py` (`project_id`, `PROJECT_FILE`), `models/identity.py`
     (preferences);
   - `schemas/platform_settings.py`;
   - `tests/security/test_rls_workspace.py`, `tests/integration/test_demo_reset.py`;
   - the ZAP trial: `Makefile` `zap`, `scripts/zap/`.
2. **Tasks, Kanban and evidence:**
   - backend: `algorithms/positions.py`, `services/workspace.py`, `services/tasks.py`,
     `repositories/tasks.py`, `schemas/tasks.py`, `api/v1/tasks.py`, `core/authz.py`;
   - frontend: `features/workspace/{WorkspaceLayout,TasksTab,KanbanBoard,TaskDrawer,NewTaskForm,api}.tsx`;
   - tests.
3. **Check-ins:** `services/checkins.py`, `schemas/checkins.py`, `api/v1/checkins.py`,
   `jobs/monitoring_jobs.py` (reminders), `CheckinsTab.tsx`, tests.
4. **Comments with mentions:** `services/comments.py`, `api/v1/comments.py`, `lib/linkify.ts`,
   `components/Comments.tsx`, the mention picker, tests.
5. **Activity events:** `schemas/activity.py`, `services/activity.py`, the Phase 8 hooks in
   `services/team.py`, tests.
6. **Monitoring:**
   - backend: `algorithms/risks.py`, `algorithms/forecast.py` (D161), `core/cache.py`,
     `services/monitoring.py`, `services/projects.get_plan`, `api/v1/monitoring.py`, the jobs,
     `jobs/scheduler.py`, `core/task_queue.py`, the `risk_critical` template;
   - frontend: `OverviewTab`, `TimelineTab` (+ `Gantt.tsx` layers and `CpmList`), `MilestonesTab`,
     `RisksTab`, `RiskList`, `BudgetDonut`;
   - tests.
7. **Seed and gate:** `scripts/seed_demo.py` (+ `seed_data/inventory.py`),
   `scripts/monitoring_check.py`, `phase_gate.py` `phase9_checks`, `Makefile` `DAY`.
8. **Files:** `services/project_files.py`, `uploads/pipeline.py` (`PROJECT_FILE`),
   `services/files.py` (`purge_orphans`), `api/v1/project_files.py`, `FilesTab.tsx`, tests.
9. **Discussion:** `services/discussion.py`, `api/v1/discussion.py`, `DiscussionTab.tsx`, tests.
10. **Notifications:**
    - backend: `core/notification_types.py`, `services/notifications.py` (async `notify`,
      preferences, publish), every `notify`/`enqueue` caller, `services/outbox.py`, `api/v1/notifications.py`
      (stream, preferences), `infra/nginx/nginx.conf`;
    - frontend: `features/notifications/{useNotificationStream,PreferencesSection}.tsx`, `AppShell`
      bell;
    - tests.
11. **Evidence tab, My projects, dashboards:** `EvidenceTab.tsx`, `features/projects/MyProjectsPage.tsx`,
    `api/v1/me.py` (`/me/projects`), `features/home/*`, `navigation.ts`, `@tanstack/react-virtual`
    (`npx npm@10 install --save-exact`), tests.
12. **DAST:** `phase_gate.py` `step_dast`, `Makefile` `zap`, the fixes ZAP finds.
13. **Finishing:**
    - E2E: `phase9.spec.ts`, `screens.ts`, `stateful-screens.ts`, baselines;
    - docs: `API.md`, `SECURITY.md`, `ALGORITHMS.md`, `ARCHITECTURE.md`, `UI_GUIDE.md`,
      `components.md`, `BACKLOG.md`, `FR_MAPPING.md`, `TESTING.md`, `OWNERSHIP.md`, `PROGRESS.md`;
    - sprint notes `sprint-07.md` and `sprint-08.md`;
    - `/security-review` → `docs/security-reviews/phase-09.md`.

Each numbered item gets at least one `phase-9: <what>` commit and a short report to Sara.

## Commands

- **The gate (Taeen, native Linux):** `make gate PHASE=9` (20 steps; step 16 GPU and step 17 DAST
  need the full machine).
- **Here, per step:**
  - `pytest -m "unit or property"`;
  - `npx vitest run` on the changed files.
- **Here, before each push:**
  - `python3 backend/scripts/phase_gate.py --phase 9 --only lint,types,static-security,forbidden,migrations`;
  - the placeholder grep (`arrives in Phase|My projects|phase: 9`);
  - the backend suite in the test stack (`… run --rm -T tests pytest -q -m "not perf and not chaos
    and not fuzz"`) with the dev stack idle;
  - the security suite;
  - `make fuzz`;
  - `npx vitest run`;
  - Phase 9 E2E and stateful screens on Chromium (plus Firefox and WebKit once);
  - `make zap`;
  - `make demo-reset STAGE=2` (< 30 s, invariants printed).
- **After any API change:** rebuild the test image, then `make openapi`, then `npm run api:types`.

## Risks and mitigations

- **Size versus Demo 2 (biggest):** 14 tables, about 35 operations and 11 tabs on a slow WSL
  laptop.
  - *Mitigation:* the demo path comes first (items 1–7 by about day 3); commit and report per
    item.
  - Notification preferences are the only item allowed to move to Demo 3 (D153), and only if the
    walkthrough is at risk.
- **ZAP's first run on the whole app:** findings from Phases 1–8 (headers on error and 304
  responses, cookies, cache headers).
  - *Mitigation:* the day-1 trial; fix each at its cause in Nginx or the middleware; never relax a
    rule.
- **Seed exactness (p = 0.7 / 0.4, only the documented risks):**
  - *Mitigation:* a hand-built worked table in `ALGORITHMS.md` first, then the seed asserts it.
  - Any detail §18.2 leaves open that I adjust gets a decision entry.
- **`ALTER TYPE … ADD VALUE` inside a migration:**
  - *Mitigation:* an `autocommit_block`, with no use of the new value in the same transaction
    (the CHECK compares `kind::text`).
  - The downgrade test runs up → down → up in the test stack.
- **Making `notify` async touches about 20 Phase 5–8 call sites:**
  - *Mitigation:* a mechanical change, plus a grep test that every call is awaited and typed.
  - The full Phase 5–8 suites run before the commit.
- **Races (concurrent moves, double check-ins, evaluation versus moves):**
  - *Mitigation:* a consistent lock order (project → milestone → task → dependents), advisory
    locks for position keys and evaluation, and unique indexes.
  - Each case gets a concurrent test that opens connections a few at a time (D117).
- **Visual baselines and timing flakes on this laptop:**
  - *Mitigation:* mask volatile text, run suites with the dev stack idle, and confirm baselines
    twice on fresh data.
  - The workspace-team and shell baselines change because of D160: only those are regenerated, and
    each is reviewed by eye.
- **The gate's GPU step and full-run timings can't be checked here:** Taeen runs the gate. Every
  other check runs here first.
