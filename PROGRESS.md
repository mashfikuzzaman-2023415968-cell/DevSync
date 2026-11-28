# DevSync progress

## Current state
- **Current owner:** Sara Binte Shafayet (tester), Phases 9–11, from 2026-11-27 (start prompt `phase-09-start-prompt.md`; Raisa owned Phases 6–8 until 2026-11-25).
- **Current phase:** 9 (workspace and monitoring) is **in progress** on `phase-9` (Sara with Claude Code; plan `docs/plans/phase-09.md`, decisions D141–D174). Done and committed: the plan, migration 0016 with RLS. Built and being verified: tasks and the Kanban board, check-ins and reminders, comments with mentions, evidence events and the Phase 8 hooks, the risk engine, monitoring and the forecast with the Overview, Timeline, Milestones and Risks tabs, and the Inventory dashboard seed with `phase9_checks`. Still to build (D159 order): project files, discussion, the notification stream and preferences, the Evidence tab, My projects and the dashboards, then DAST and the finishing work.
- **Phase 8:** done (gate PASS 2026-11-25 05:11 Asia/Dhaka on Taeen's laptop), merged to `main`, tagged `phase-8`.
- **Last gate result:** Phase 8 PASS, 2026-11-25 05:11 Asia/Dhaka (`runs/gate-p8b.log`): backend 2,105 (95.1%), security 600, contract 701, frontend 568 (81.0%), E2E 93, a11y 36, visual 143 (232 baselines), Lighthouse desktop 100/100/96/100 and mobile 94/100/96/100, GPU 5/5, algorithm budgets met, phase checks (repair, lead, team RLS/API) and regression guard clean. One fix was needed (D140). Both tests Raisa flagged as timing-sensitive on WSL passed here.
- **Verified on Raisa's laptop (WSL 2, 2026-11-24):** backend suite 2,103 passed, 1 failed (`test_admin_limit_is_per_user`, the timing-sensitive test already listed under Known issues; it failed the same way here in Phase 6), coverage 95.25 %; the Phase 8 API/unit/RLS/algorithm/authz tests 59/59 after the last changes; repair perf (10 candidates, 4 members: PSO ≈ 1.4 s, exact 0.05 s, budget 5 s); frontend 568 Vitest; full Chromium `@e2e|@a11y` 128 passed, 1 failed (`phase5 › after the bidding deadline the bid sheet is closed`, a 5 s wait against this laptop's 3–5 s repaint after a reload; it failed the same way in the Phase 6 gate attempt here, untouched); Phase 8 E2E passes (the whole flow, axe and layout on the new screens); visual: 122 existing screenshot tests match, 3 baselines updated (bell badge, team-card order), 12 new reviewed by eye; stage-2 seed builds the repair demo and `repair_check.py` passes (seeded READY with 1 candidate; scripted decline → 2 ranked); `formation_check.py` reproduces the D116 team; OpenAPI 0 problems; fuzz + property 715 passed and 1 real bug found (the admin removal list returned 500 once a request existed; fixed and tested, its 20 fuzz cases pass).
- **In progress:** Phase 9 items 2–7 of D159 (see the session log); then items 8–12.
- **Very next step:** finish verifying the Inventory seed (`monitoring_check.py`), commit, then project files (item 8). Gates run on Taeen's native Linux laptop, plugged into the original Dell charger.
- **Open human tasks:** review the 128 drafted test questions (D34); tester's human check of the Phase 3–8 security reviews; sanity-check D39 (simulated payment-method verification). `make demo-reset STAGE=2` was measured on Sara's laptop on 2026-11-27 before Phase 9 at 23 s (target < 30 s); measure it again with the Inventory project.
- **Sprint notes:** they stopped at `sprint-03.md`; from Phase 9 they resume at `sprint-07.md` (23–29 Nov) without back-filling sprints 4–6.

## Phase table
| Phase | Owner | Status | Gate | Date | Tag |
|---|---|---|---|---|---|
| 0 Foundations | Taeen | done | PASS | 2026-10-17 | phase-0 |
| 1 Accounts & security core | Taeen | done | PASS | 2026-10-17 | phase-1 |
| 2 Design system & landing | Taeen | done | PASS | 2026-10-17 | phase-2 |
| 3 Profiles & skill tests | Taeen | done | PASS | 2026-10-18 | phase-3 |
| 4 Projects & CPM | Salwa (review fixes: Taeen) | done | PASS | 2026-10-20 | phase-4 |
| 5 Marketplace & filtering | Salwa (gate fixes: Taeen) | done | PASS | 2026-10-21 | phase-5 |
| 6 Reputation & simulator | Raisa (gate fixes: Taeen) | done | PASS | 2026-11-22 | phase-6 |
| 7 Team formation | Raisa (gate fixes: Taeen) | done | PASS | 2026-11-23 | phase-7 |
| 8 Invitations, lead, repair | Raisa (gate fix: Taeen) | done | PASS | 2026-11-25 | phase-8 |
| 9–15 | — | not started | — | — | — |

## Gate log (newest first, appended by `make gate`)
| Finished (UTC) | Phase | Result | Tests |
|---|---|---|---|
<!-- gate-log -->
| 2026-11-24T23:11:54+00:00 | phase 8 | PASS | backend 2105 / frontend 568 tests |
| 2026-11-24T21:28:46+00:00 | phase 8 | FAIL (step 15) | backend 2104 / frontend 568 tests |
| 2026-11-23T15:09:43+00:00 | phase 7 | PASS | backend 2044 / frontend 545 tests |
| 2026-11-23T13:45:54+00:00 | phase 7 | FAIL (step 16) | backend 2044 / frontend 545 tests |
| 2026-11-23T12:19:52+00:00 | phase 7 | FAIL (step 13) | backend 2044 / frontend 545 tests |
| 2026-11-23T11:07:15+00:00 | phase 7 | FAIL (step 9) | backend - / frontend - tests |
| 2026-11-23T09:58:24+00:00 | phase 7 | FAIL (step 7) | backend - / frontend - tests |
| 2026-11-23T09:54:12+00:00 | phase 7 | FAIL (step 9) | backend - / frontend - tests |
| 2026-11-23T06:26:30+00:00 | phase 7 | FAIL (step 9) | backend - / frontend - tests |
| 2026-11-23T04:45:46+00:00 | phase 7 | FAIL (step 7) | backend - / frontend - tests |
| 2026-11-23T04:02:46+00:00 | phase 7 | FAIL (step 6) | backend - / frontend - tests |
| 2026-11-22T00:15:26+00:00 | phase 6 | PASS | backend 1857 / frontend 527 tests |
| 2026-11-21T22:55:00+00:00 | phase 6 | FAIL (step 13) | backend 1857 / frontend 527 tests |
| 2026-11-21T21:54:13+00:00 | phase 6 | FAIL (step 11) | backend 1850 / frontend - tests |
| 2026-11-21T21:03:52+00:00 | phase 6 | FAIL (step 9) | backend - / frontend - tests |
| 2026-11-21T18:50:06+00:00 | phase 6 | FAIL (step 9) | backend - / frontend - tests |
| 2026-11-20T14:12:10+00:00 | phase 5 | FAIL (step 11) | backend 1694 / frontend - tests |
| 2026-11-20T13:12:16+00:00 | phase 5 | FAIL (step 11) | backend 1694 / frontend - tests |
| 2026-11-20T08:15:06+00:00 | phase 5 | FAIL (step 13) | backend 1694 / frontend 506 tests |
| 2026-11-20T05:23:55+00:00 | phase 5 | FAIL (step 11) | backend 1661 / frontend - tests |
| 2026-11-19T18:10:28+00:00 | phase 5 | FAIL (step 9) | backend - / frontend - tests |
| 2026-11-19T17:47:28+00:00 | phase 5 | FAIL (step 9) | backend - / frontend - tests |
| 2026-11-19T17:24:56+00:00 | phase 5 | FAIL (step 11) | backend 1644 / frontend - tests |
| 2026-11-19T16:38:06+00:00 | phase 5 | FAIL (step 13) | backend 1644 / frontend 506 tests |
| 2026-11-19T14:30:59+00:00 | phase 5 | FAIL (step 7) | backend - / frontend - tests |
| 2026-11-09T12:55:22+00:00 | phase 5 | FAIL (step 7) | backend - / frontend - tests |
| 2026-11-08T18:41:11+00:00 | phase 5 | FAIL (step 15) | backend 1629 / frontend 499 tests |
| 2026-11-08T15:29:20+00:00 | phase 5 | FAIL (step 13) | backend 1629 / frontend 499 tests |
| 2026-11-08T13:24:36+00:00 | phase 5 | FAIL (step 7) | backend - / frontend - tests |
| 2026-11-05T15:53:48+00:00 | phase 5 | FAIL (step 13) | backend 1592 / frontend 485 tests |
| 2026-11-05T13:51:03+00:00 | phase 5 | FAIL (step 7) | backend - / frontend - tests |
| 2026-11-05T12:27:21+00:00 | phase 5 | FAIL (step 2) | backend - / frontend - tests |
| 2026-11-03T22:24:56+00:00 | phase 5 | FAIL (step 13) | backend 1592 / frontend 485 tests |
| 2026-11-03T17:05:21+00:00 | phase 5 | FAIL (step 13) | backend 1592 / frontend 485 tests |
| 2026-11-02T21:51:13+00:00 | phase 5 | FAIL (step 9) | backend - / frontend - tests |
| 2026-11-02T19:33:15+00:00 | phase 5 | FAIL (step 9) | backend - / frontend - tests |
| 2026-11-02T17:26:31+00:00 | phase 5 | FAIL (step 13) | backend 1592 / frontend 485 tests |
| 2026-10-30T14:18:43+00:00 | phase 5 | FAIL (step 9) | backend - / frontend - tests |
| 2026-10-30T13:40:30+00:00 | phase 5 | FAIL (step 10) | backend 1590 / frontend - tests |
| 2026-10-30T09:50:00+00:00 | phase 5 | FAIL (step 13) | backend 1590 / frontend 484 tests |
| 2026-10-29T21:07:55+00:00 | phase 5 | PASS | backend 1588 / frontend 484 tests |
| 2026-10-29T17:43:17+00:00 | phase 5 | FAIL (step 2) | backend - / frontend - tests |
| 2026-10-29T17:33:42+00:00 | phase 5 | FAIL (step 11) | backend 1577 / frontend - tests |
| 2026-10-29T16:46:35+00:00 | phase 5 | FAIL (step 13) | backend 1577 / frontend 484 tests |
| 2026-10-29T15:18:49+00:00 | phase 5 | FAIL (step 11) | backend 1577 / frontend - tests |
| 2026-10-29T13:44:06+00:00 | phase 5 | FAIL (step 13) | backend 1577 / frontend 484 tests |
| 2026-10-29T04:08:52+00:00 | phase 5 | FAIL (step 13) | backend 1577 / frontend 484 tests |
| 2026-10-28T22:13:37+00:00 | phase 5 | FAIL (step 9) | backend - / frontend 484 tests |
| 2026-10-28T20:00:44+00:00 | phase 5 | FAIL (step 6) | backend - / frontend - tests |
| 2026-10-27T01:21:22+00:00 | phase 5 | PASS | backend 1215 / frontend 458 tests |
| 2026-10-26T16:36:47+00:00 | phase 5 | FAIL (step 11) | backend 1209 / frontend - tests |
| 2026-10-26T14:03:03+00:00 | phase 5 | FAIL (step 11) | backend 1202 / frontend - tests |
| 2026-10-26T12:41:23+00:00 | phase 5 | FAIL (step 7) | backend - / frontend - tests |
| 2026-10-26T12:10:24+00:00 | phase 5 | FAIL (step 6) | backend - / frontend - tests |
| 2026-10-26T11:10:14+00:00 | phase 5 | FAIL (step 5) | backend - / frontend - tests |
| 2026-10-26T08:32:28+00:00 | phase 5 | FAIL (step 5) | backend - / frontend - tests |
| 2026-10-26T07:33:51+00:00 | phase 5 | FAIL (step 3) | backend - / frontend - tests |
| 2026-10-24T05:03:15+00:00 | phase 5 | FAIL (step 7) | backend - / frontend - tests |
| 2026-10-23T19:22:37+00:00 | phase 5 | FAIL (step 13) | backend 865 / frontend 334 tests |
| 2026-10-23T12:15:25+00:00 | phase 5 | PASS | backend 839 / frontend 306 tests |
| 2026-10-23T10:36:53+00:00 | phase 5 | FAIL (step 13) | backend 839 / frontend 306 tests |
| 2026-10-23T08:19:31+00:00 | phase 5 | FAIL (step 5) | backend 839 / frontend 305 tests |
| 2026-10-22T20:01:35+00:00 | phase 5 | PASS | backend 839 / frontend 291 tests |
| 2026-10-22T18:24:59+00:00 | phase 5 | FAIL (step 12) | backend 839 / frontend - tests |
| 2026-10-22T18:06:59+00:00 | phase 5 | PASS | backend 839 / frontend 291 tests |
| 2026-10-22T14:17:43+00:00 | phase 5 | FAIL (step 13) | backend 839 / frontend 291 tests |
| 2026-10-22T12:36:38+00:00 | phase 5 | PASS | backend 839 / frontend 291 tests |
| 2026-10-22T10:47:58+00:00 | phase 5 | FAIL (step 13) | backend 839 / frontend 291 tests |
| 2026-10-22T09:26:09+00:00 | phase 5 | FAIL (step 13) | backend 839 / frontend 291 tests |
| 2026-10-22T05:58:19+00:00 | phase 5 | FAIL (step 13) | backend 785 / frontend 283 tests |
| 2026-10-21T20:00:03+00:00 | phase 5 | PASS | backend 785 / frontend 283 tests |
| 2026-10-21T17:12:45+00:00 | phase 5 | FAIL (step 13) | backend 778 / frontend 283 tests |
| 2026-10-21T14:14:09+00:00 | phase 5 | FAIL (step 13) | backend 775 / frontend 283 tests |
| 2026-10-21T11:35:34+00:00 | phase 5 | FAIL (step 3) | backend 775 / frontend 278 tests |
| 2026-10-19T20:26:29+00:00 | phase 4 | PASS | backend 716 / frontend 269 tests |
| 2026-10-19T20:05:41+00:00 | phase 4 | FAIL (step 3) | backend 716 / frontend 269 tests |
| 2026-10-19T19:17:13+00:00 | phase 4 | PASS | backend 716 / frontend 267 tests |
| 2026-10-19T16:34:19+00:00 | phase 4 | FAIL (step 13) | backend 716 / frontend 267 tests |
| 2026-10-19T15:53:38+00:00 | phase 4 | FAIL (step 13) | backend 716 / frontend 267 tests |
| 2026-10-19T15:20:24+00:00 | phase 4 | FAIL (step 13) | backend 716 / frontend 267 tests |
| 2026-10-19T13:15:27+00:00 | phase 4 | FAIL (step 5) | backend - / frontend - tests |
| 2026-10-19T13:12:14+00:00 | phase 4 | FAIL (step 4) | backend - / frontend - tests |
| 2026-10-19T13:08:46+00:00 | phase 4 | FAIL (step 3) | backend - / frontend - tests |
| 2026-10-19T13:06:36+00:00 | phase 4 | FAIL (step 3) | backend - / frontend - tests |
| 2026-10-19T06:08:02+00:00 | phase 3 | FAIL (step 13) | backend 674 / frontend 244 tests |
| 2026-10-19T05:27:47+00:00 | phase 3 | FAIL (step 12) | backend 674 / frontend - tests |
| 2026-10-19T05:09:26+00:00 | phase 3 | FAIL (step 12) | backend 674 / frontend - tests |
| 2026-10-19T04:44:45+00:00 | phase 3 | FAIL (step 6) | backend - / frontend - tests |
| 2026-10-18T20:25:28+00:00 | phase 3 | FAIL (step 7) | backend - / frontend - tests |
| 2026-10-18T06:26:08+00:00 | phase 3 | PASS | backend 640 / frontend 244 tests |
| 2026-10-18T06:07:55+00:00 | phase 3 | FAIL (step 3) | backend 640 / frontend 244 tests |
| 2026-10-17T16:43:18+00:00 | phase 2 | PASS | backend 445 / frontend 218 tests |
| 2026-10-17T16:20:47+00:00 | phase 2 | FAIL (step 7) | backend 445 / frontend 0 tests |
| 2026-10-17T14:03:25+00:00 | phase 2 | FAIL (step 9) | backend - / frontend - tests |
| 2026-10-17T12:42:39+00:00 | phase 2 | FAIL (step 5) | backend - / frontend 217 tests |
| 2026-10-17T07:17:01+00:00 | phase 1 | PASS | backend 417 / frontend 132 tests |
| 2026-10-17T06:19:59+00:00 | phase 1 | FAIL (step 13) | backend 417 / frontend 130 tests |
| 2026-10-17T06:10:47+00:00 | phase 1 | FAIL (step 5) | backend - / frontend 130 tests |
| 2026-10-17T04:48:38+00:00 | phase 0 | PASS | backend 182 / frontend 52 tests |
| 2026-10-17T04:45:33+00:00 | phase 0 | FAIL (step 9) | backend - / frontend 52 tests |
| 2026-10-17T04:40:20+00:00 | phase 0 | FAIL (step 7) | backend - / frontend 52 tests |
| 2026-10-17T04:28:22+00:00 | phase 0 | FAIL (step 3) | backend - / frontend 52 tests |

## Known issues
- This laptop runs Apache on port 80: for `make up`, set `HTTP_PORT=8080` in `.env` or stop Apache.
- `make certs` produced a self-signed certificate; install mkcert before Demo 1 (D3). Still open on 2026-10-27: `make demo-preflight` warns, and browsers will show a certificate warning until `mkcert -install && make certs FORCE=1` (then restart nginx).
- Node 20 is end-of-life and unpatched for CVE-2026-111497 ("Node2Shell", Brotli); not exposed at runtime (no Node in the served images, Nginx builds only the Brotli encoder), but move the laptops and the edge build stage to Node 22 LTS at the start of Phase 6 (D15).
- Tester's human check of `docs/security-reviews/phase-00.md` to `phase-03.md` is pending (Sara).
- The 128 skill-test questions need a human accuracy review (D34).
- The gate's frame-rate step needs a GPU (`/dev/dri`); run the gate on a laptop (D28). Long gate runs are best started with `systemd-run --user` so closing a terminal or chat doesn't kill them.
- The 2021 STI paper is cited without a link (no DOI found); add the IEEE Xplore URL when known.
- Existing dev databases: run `make migrate` (migration 0002); create an admin with `make create-admin`.
- Phase 5 known limitations (D54): TOO_SLOW compares with the whole-project deadline, not the slot's milestones (the paper's simplification); availability must be re-checked when invitations are accepted (Phase 8); bid prices stay visible to the client during bidding (spec), sealed from other developers.
- Docker's build cache can keep an old `apt-get` layer: on 2026-10-26 a cached layer held a `libbrotli1` with a HIGH CVE that Trivy failed. Build images for a demo or a deployment with `--no-cache` (the demo stack was rebuilt that way on 2026-10-27).
- The full gate needs about 3 GB of free memory (7 GB laptop): close Chrome first.
- **Gate laptop power (2026-11-23):** on a weak or loose charger the Dell G15 reports "Not charging" and holds the CPU at ~400 MHz; step 9 then can't finish in 60 minutes. Use the original Dell barrel charger and check `cat /sys/class/power_supply/BAT*/status` before a gate. Start long runs with `systemd-inhibit --what=sleep:idle:handle-lid-switch` so closing the lid doesn't suspend them. Under swap pressure WebKit E2E runs time out, and those failures say nothing about the code.

- **Gate step 16 can't pass on WSL 2 (checked 2026-11-21).** `/dev/dri/renderD128` exists under WSLg, but inside the GPU Playwright image Chromium falls back to `llvmpipe` (software), and the `@perf|@gpu` tests correctly refuse it (5 failed). The real GPU is reached through `/dev/dxg` (Direct3D 12); the image has no Vulkan-on-D3D12 driver. Run the gate on a native Linux laptop (D28), or decide (with Taeen) whether to extend the GPU image for WSL.
- **Load flakes seen on this WSL laptop (2026-11-21), all Phase 1–5 screens, none changed:** `login-totp` responsive (the sign-in CAPTCHA asked to "complete the verification check again"), `app shell light 390` visual (profile page slow to load) and `assessment-required light 768` visual (a 401 while its setup published a project). Each passed 2/2 when re-run alone, matching its baseline. Watch them in the gate.
- **Visual baselines (2026-11-21):** 6 new — `reputation-experienced-{light,dark}-{390,768,1440}.png`, reviewed by eye (labels 12 px at every width after the chart-sizing fix); no existing baseline changed (the full `@visual` run matched all 202).
- **`test_admin_limit_is_per_user` is timing-sensitive on slow machines.** It sends 300 admin requests that must all land inside a 60-second window. Alone on this WSL laptop it passes 3/3 but takes 52–54 s; under the full suite it went over and failed. Not a Phase 6 change; not modified. Watch it in the gate on a faster machine; if it fails there too, fix the test's timing at the cause (not by loosening the limit).

## Session log (newest first)
### 2026-11-27 — Sara (with Claude Code), Phase 9 start and build (WSL 2 laptop)
- **Setup:**
  - Laptop set up: Ubuntu 26.04 on WSL 2, Docker 29.6, Node 22, uv, make, jq and mkcert; there is
    no `/dev/dri`, so gate step 16 runs on Taeen's laptop.
  - `main` at `f7fedc1`.
  - Unit tests 1,003 passed; Vitest 563 + 5 skipped.
  - Stage 2 verified by hand, including starting the Clinic team through the API.
  - `demo-reset STAGE=2` takes 23 s.
- **Plan and decisions:** written and approved; D141–D159 (the brief's decisions), D160–D161 from
  the study, D162–D172 from planning, D173–D174 during the build.
- **Item 1:**
  - Migration 0016 with RLS, `record_activity()` and the guard triggers, plus settings v6.
  - 15 RLS tests; migrating up, down and up again is clean; `check_rls` reports 0 unprotected
    tables.
- **Items 2–7, built:**
  - tasks and the Kanban board (one-step moves, fractional positions, dependencies, evidence);
  - weekly check-ins and the Monday reminders job;
  - comments with mentions and the safe linkifier;
  - all 22 evidence event schemas, plus the Phase 8 hooks (`member.left`, `member.replaced`,
    unassigning a departing member's tasks);
  - `member_inactive_days` with its real body (D150);
  - the pure risk engine, `monitoring.evaluate` (sweep, debounced flush, CRITICAL notices) and the
    cached role-shaped dashboard;
  - the forecast on the plan, which members can now read;
  - the Overview, Tasks, Timeline, Milestones, Check-ins and Risks tabs, and the plan page's
    baseline-vs-forecast view;
  - the Inventory dashboard seed (`DAY`, D170, D174), `monitoring_check.py` and `phase9_checks`.
- **Tests on this laptop:**
  - the backend set for items 2–6 plus the Phase 8 team suite: 665 passed and 6 failed, all six
    in my new tests or reads; all fixed, and the comments, monitoring, sessions and HTTP-hardening
    files pass (92 + 19);
  - one of the six was a bug in the test helper, not the app: `Api.request` called
    `headers.setdefault("X-CSRF-Token", self.csrf_token())`, which fetches a new cookie even
    when the caller sends its own token, so the two never matched. It now fetches only when no
    token was given;
  - full backend suite in the test stack: 3,139 passed, 2 failed. The `comment` scope was still
    listed as pending in `test_rate_limits.py` (moved to tested). The other was a schemathesis
    10 s read timeout on `POST /me/certificates`, which schemathesis itself couldn't reproduce;
    both pass on a re-run;
  - frontend: lint and typecheck clean, Vitest 48 files passed and 1 skipped;
  - `demo-reset` + `seed_demo.py --stage 2` in the test stack: Inventory day 12 forecasts 25
    (+2), CRITICAL_PATH_DELAY CRITICAL, DEADLINE_IMPACT, INACTIVE_MEMBER and SLACK_EATEN MEDIUM,
    health At risk; `monitoring_check.py` passes and is idempotent; `formation_check.py`
    unchanged (16.18 %).
- **Item 8 (project files, 2026-11-28):**
  - upload, list and soft delete;
  - §14.9 types only (Markdown keeps `.md`, served as plain text);
  - 20 uploads an hour and a reserved daily byte budget (D175), failing closed when Redis is
    down;
  - evidence links shown in the list; the orphan cleanup keeps deleted project files;
  - the Files tab, and file or screenshot evidence in the task drawer.
  - Fixed on the way:
    - the upload path was missing from `UPLOAD_PATHS`, so it got 415 (Nginx already had it);
    - a lead couldn't soft-delete a member's file under RLS. PostgreSQL checks the updated
      row against the SELECT policies, so `project_file_select` in 0016 now lets the lead see
      deleted rows of the project (D175). The test stack's database got the same policy by
      hand; the gate migrates a fresh one.
  - Tests:
    - backend: 110 passed (project files, RLS workspace, authz matrix, profile files, jobs);
    - unit and rate limits: 943 passed;
    - frontend workspace: 96 passed;
    - OpenAPI check: 0 problems.
- **Item 9 (discussion, 2026-11-28):**
  - threads with a first post, ordered by latest activity; posts with mentions, replies,
    15-minute edits (revisions kept) and soft delete;
  - `comment.posted` / `comment.replied` recorded with `DISCUSSION_POST`;
  - shares the 60/hour `comment` limit;
  - admins: 403 on the project's thread list, and 404 on a thread id (RLS hides thread rows
    from them);
  - the Discussion tab (list and thread, `?thread=` from notifications, 15-second polling)
    reuses `Comments`, which gained optional labels.
  - Tests: backend 24 passed (and 117 with the rate-limit and event-schema suites); frontend
    173 passed; OpenAPI check: 0 problems.
- **Item 10 (notifications, 2026-11-28):**
  - the catalogue (`core/notification_types.py`): 32 types in 13 §12 categories; anything
    outside it is refused;
  - `notify` is now async and honours the in-app switch;
  - `outbox.enqueue` honours the email switch for every non-account template (the six account
    templates are always sent);
  - new emails: `mentioned` (opt-in), `checkin_reminder`, `risk_critical`;
  - the new-bids job now goes through `notify`;
  - new notifications are published to Redis after commit (dropped on rollback);
  - `GET /notifications/stream` (SSE, D107 rules, shared 3-stream limit, `Last-Event-ID`
    replay) with its own Nginx location;
  - preferences GET/PUT, audited;
  - frontend: `useNotificationStream` in the app shell, with backoff when the browser gives up
    and the 60 s refresh kept as the fallback; the notification switches on Settings; a link
    from Notifications. Decisions: D176.
  - Tests: backend 125 passed (catalogue, live and preference tests plus every suite that sends
    notifications) and 47 with the edge tests; frontend 27 passed; OpenAPI check: 0 problems.
- **Laptop notes:**
  - BuildKit crashes ("frontend grpc server closed") when `tests` and `api` are built in one
    `compose build`, or alongside other load; building them one at a time works every time.
  - The ZAP image took 55 minutes to pull here.
  - Long suites need the dev stack stopped (memory).

### 2026-11-25 — Taeen (with Claude Code), Phase 8 gate on the native Linux laptop
- Ran `make gate PHASE=8` on Raisa's `phase-8` (`495cc4b`); two full runs. The first failed step 15: the 12 new `client-team-repair` and `workspace-team` baselines showed the same content in another order. Members created together tie on `created_at` and fell back to random ids; open slots were listed by random id; the recommended lead followed the acceptance order and changed too. Fix (D140): the team view sorts members by role, then name, and the blockers by role; a test pins it; the 12 baselines were re-created and matched twice on fresh data. Second run PASS (`runs/gate-p8b.log`).
### 2026-11-23 to 2026-11-24 — Raisa (with Claude Code), Phase 8 build
- Plan approved (`docs/plans/phase-08.md`); decisions D118–D136 from the start prompt, D137–D139 resolving open points (one bid per developer on a reopened place; repair impact arithmetic; the stage-2 golden file moved to `scripts/seed_data/` so `make demo-up STAGE=2` works in the production image).
- Migration 0015: lead-change requests, repair proposals (immutable inputs, never deleted), removal requests, `lead_declined_at`, reopened places; `is_team_member()` counts only current members (D130); SYSTEM-only writes, and SYSTEM may now update milestones, slots and baselines (start silently activated nothing before).
- Pure `lead.py` (§1.6 rule 1, tie-breaks, reason) and `repair.py` (locked members, top three, newcomer minimum, no-candidate reasons, CPM impact with a hand-computed test and a worked example in ALGORITHMS.md).
- Services, job and routes: invitations sent on confirm and by `lifecycle.expire`, accept with the free-hours re-check, decline, expiry; lead choose/decline/change and requests; start (D118, D119); leave; removal requests (409 until Phase 9); cancel of a pending team; repair, choose replacement, reopen place, raise budget; notifications read API; emails. Asserts replaced by explicit fail-closed checks after the forbidden-pattern scan.
- Frontend: client Team screen (#25), Teams list, dashboard invitation banners with a countdown, workspace shell with the Team tab (#33), notifications page (#18) and bell count, open places on cards and the bid sheet, next-action links; the workspace tab bar was widening phones (sr-only notes outside the scroller) and the muted tabs failed AA, both fixed.
- Stage-2 seed: "Clinic appointment booking" TEAM_PENDING with one decline and a READY repair, built through the real services; `repair_check.py` and `phase8_checks` in the gate; repair perf test; Phase 8 E2E; new stateful screens in axe, the viewport matrix and visual baselines.

### 2026-11-23 — Taeen (with Claude Code), Phase 7 gate on the native Linux laptop
- Ran `make gate PHASE=7` on Raisa's `phase-7` (`c37fb9e`); nine full runs. Fixes (D117, none in the formation logic, nothing relaxed): `# forbidden-ok` on the `one_active_lead_per_team` predicate; 46 unit tests for `app/core/task_queue.py` and `app/services/formation_runner.py`; Nginx image rebuilt `--no-cache --pull` (krb5 CVEs); `test_concurrent_writers_keep_one_unbroken_chain` opens its 30 connections five at a time and releases the writers at a barrier (asyncpg's Python SCRAM made 30 simultaneous connects exceed the 3 s connect timeout); `check_paper_alignment` test fixture extended to Eq. 13–19 and a missing formation module reported, not raised; E2E auth helpers wait out Nginx's `auth` zone (HTML 429 only) and `csrfHeaders` fails clearly; the GPU homepage test expects the real cost-of-fairness chip (D113).
- Not code: one run stopped at step 7 on a network drop; one was paused two hours by a closed lid (runs now also block `handle-lid-switch`); two timed out at step 9 because the laptop was on a charger that didn't deliver enough power (battery "Not charging", CPU held at 400 MHz) — fixed by the original Dell charger and a reboot.
- Run 9: **PHASE 7 GATE: PASS**. Committed, merged to `main`, tagged `phase-7`.

### 2026-11-22 to 2026-11-23 — Raisa (with Claude Code), Phase 7 build
- Carried over the audit-chain fix (0013, D103) and the per-screen CSP/axe checks (D104).
- Pure algorithms: fitness Eq. 17–19, binary PSO (Algorithm 2) with repair, exact solver, fairness dial, explanations (risks, comparison, why this team, why not selected with a property-tested price counterfactual), greedy baseline, `run_formation`; presets D115; E1 script.
- Migration 0014 (runs with immutable inputs, explanations sealed to the bidder, teams, members, unsent invitations; SYSTEM-only writes). Generic jobs API + SSE with an unbuffered Nginx location (D107). Formation service, runner, jobs and endpoints (D106, D108–D110), admin verify with step-up.
- Frontend: team formation screen (presets, priority sliders, standards, fairness dial, live swarm and convergence, team cards, why this team, comparison, runs, confirm), "why it wasn't selected" card; slider thumbs and breadcrumb links got 44 px touch targets.
- Stage-2 seed leaves the ordering project FORMING (D116); `formation_check.py` gate check + homepage fairness figures from the real run (D113).
- Bugs found and fixed while testing: evaluation must run in a SYSTEM session (D50); a sync Redis dependency shared one client across event loops (`loop_redis`); a non-selected bidder couldn't read their explanation (joined to a team RLS hides); touch targets; contribution bars were rose for every cost.
### 2026-11-22 — Taeen (with Claude Code), Phase 6 gate on a native Linux laptop
- Ran `make gate PHASE=6` on Raisa's `phase-6` (`45247ca`). Runs 1–2 stopped at step 9: two rate-limit tests failed under memory pressure, then the step hit its 60-minute limit (the cut-off run finished on its own: 1,850 passed, 0 failed). No test or limit was changed; later runs took 19 minutes.
- Run 3 failed step 11: schemathesis sent `budget_min=370372298551098867712` to `GET /projects/search`, which overflowed BIGINT and returned a 500 (Phase 5 code). Fixed with `le=10_000_000_000` on `budget_min`/`budget_max` (D102), tests in `tests/security/test_bids.py`, `docs/api/openapi.json` regenerated. The same run flagged `POST /me/external-reviews` for accepting a multipart "wrong type" (a number sent as text, an array sent as a file part, which are indistinguishable from valid input on the wire); it passed alone and in the next two full runs, so it was left as is.
- Run 4 failed step 13: `e2e/shell.spec.ts` still expected the Phase 2 placeholder "Reputation arrives in Phase 6". It now checks the real page (the exact "Your reputation" heading and the newcomer line), as `phase6.spec.ts` does.
- Run 5: **PHASE 6 GATE: PASS**. Committed, merged to `main`, tagged `phase-6`, pushed.

### 2026-11-21 — Raisa (with Claude Code), hand-off and Phase 6 build
- Set up the laptop (WSL 2, Ubuntu 24.04, Docker 29, Node 22, Python 3.12, uv); stack, migrations, fast tests and the demo stack (`ready (9/9)`, 10 eligible) all fine. Browser checks skipped at Raisa's request; Raisa ran `make create-admin` herself.
- Phase 6 plan approved. Built: P6-0 Node 22 (D83); Eq. 1–12 as pure functions with the change cap, newcomer values, trust formula, plain-language explanations; market simulator with personas (numpy 2.5.4); migration 0012 (history, per-skill competency, append-only log; `is_system()` writes); engine service and `reputation.recalculate_all` job; stage-2 seed with a golden fixture (10 eligible kept); `GET /developers/{id}/reputation`, `GET /me/reputation/history`; the Reputation page (ReputationPanel, radar and trend charts, "Why did this change?", newcomer card); paper-alignment check and `phase6_checks`; docs and D84–D101.
- Found and fixed: Γ⁰ ignored verified certificates (D94); the 0006 snapshot write policy accepted SYSTEM from any role (D99).
- E5 measured: Spearman 0.797 (P vs latent quality), 0.759 (C vs latent breadth + communication) (D96).
- Next: visual baselines, the gate on a native Linux machine, then Phase 7. Blockers: a gate machine with a GPU; push access.

### 2026-11-19 to 2026-11-21 — Taeen (with Claude Code), gate work after Demo 1
- Gate re-runs found and fixed: two dependency CVEs (dnspython 2.9.2, opentelemetry-api 1.45.2, D79); a flaky Firefox sign-out test (D80); a NUL character in text giving a 500 (D81); the API coercing `false`/`0` into numbers and dates (D82). Each came from a real gate failure and each fix has tests. A laptop suspend and a reboot also killed two runs (the gate now runs under a sleep inhibitor).
- Pushed with this entry: the quick sign-in tab (D78), the fixes above and the plain-wording pass on `phase_gate.py`.
- Open: `role-assessment.spec.ts:181` still times out in Firefox in some full runs (second tab to the assessment page; passes alone), so a clean full gate has not been shown on this code. Phase 6 was started without it, by Taeen's decision.

### 2026-11-09 — Taeen (with Claude Code), quick sign-in tab (D78)
- `/sandbox/sms?tab=signin`: one click signs in as a seeded demo client or developer (not admins), only where the sandbox is on (D76 switch). 15 API tests + 7 page tests; backend unit+api 1220 passed, frontend 506 passed; checked on the real demo stack. Demo stack now seeded with `DEMO_PASSWORD='DevSyncDemo#2026'` (one password for every account).

### 2026-11-08 — Taeen (with Claude Code), demo readiness for Demo 1
- Built the developer SMS inbox (`/sandbox/sms`, D76) and a fuller demo seed (D77: second client Farzana and five more open projects; no completed projects, those are stage 2).
- Gate/demo-check runs: steps 1–12 pass (1629 backend, 544 security, 521 contract, 499 frontend tests; scanners clean after rebuilding images without cache); step 13 failed on one Firefox timing test under memory pressure; the demo walkthrough passed 11 of 12 (one 502 on the seed call). Fix: the second tab waits for `domcontentloaded`. Gate re-run started 21:50.
- Wrote four role sheets for the presentation in `~/Downloads/DAA1/devsync-demo-prep/` (not in the repo).
- Open: green gate on this branch, push (token), human checks (D34 question review, tester check of the role-assessment security review), bind demo ports to 127.0.0.1 (D76 note).

### 2026-10-24 to 2026-10-27 — Taeen (with Claude Code), Demo 1 completion on `wizard-drafts`
- Closed the gaps from a review of Phases 0–5 against the spec and from two logic audits (D55–D70):
  - drafts in the create-project wizard reopen where the client left off;
  - reputation summary on profiles;
  - project details with the plan and a mini Gantt, plus role and hours filters;
  - fee, bonus pool and budget shares in the planning screens;
  - bid verdicts recorded when bidding closes;
  - reasons in plain language for developers, the full trace for clients;
  - optimistic concurrency and paging;
  - new-bid notices and the daily digest;
  - CAPTCHA difficulty read from settings;
  - request-body errors, job runs, review edits and nav prefetch;
  - hardening (D62);
  - the Demo 1 stack, texts and walkthrough tooling (D61).
- Tests went from 839 to 1215 on the backend and 306 to 458 on the frontend; visual baselines from 130 to 184. The regression baseline was raised to match.
- Root causes found on the way to a clean gate, each fixed with tests:
  - Redis clients were cached by `id(loop)`. A reused id handed a new event loop a dead loop's client, which hung the backend tests. The cache is now keyed by the loop itself.
  - Argon2 hashing ran on the event loop, causing gunicorn WORKER TIMEOUTs and 502s under WebKit E2E. It now runs on a bounded thread pool.
  - Two migrations were both numbered 0009; the later one is now 0010.
  - The `libbrotli1` CVE came from a stale build-cache layer, fixed by a `--no-cache` rebuild.
  - A multipart 400 response was undocumented in OpenAPI.
  - Visual baselines depended on volatile text, now replaced by stand-ins or masked.
- The gate now keeps a failed command's whole output in `runs/gates/failed-<stamp>.log`.
- The security review addendum (`docs/security-reviews/phase-05.md`) has no high findings.
- `make demo-check DEMO=1` passed:
  - gate: every step PASS except DAST, which is N/A until Phase 9;
  - walkthrough 12/12;
  - no API worker timeouts or kills.
- Demo stack rebuilt with `--no-cache` (Trivy: 0 HIGH/CRITICAL on both images) and started with `make demo-up STAGE=1`. `make demo-preflight` reported everything OK except one warning: the certificate is self-signed because mkcert is not installed (see Known issues).
  - OK: 2 API replicas, HTTPS edge, API docs off, Mailpit, seed loaded, demo client signs in.
- Not merged or pushed: waiting for Taeen's approval.

### 2026-10-23 — Taeen (with Claude Code), Gantt polish
- Pushed `main`, `phase-5`, `phase-5-followups` and the `phase-5` tag after the Demo 1 readiness check passed.
- Gantt (`components/Gantt.tsx`): date axis (months over days, week starts when zoomed out; days from start without a start date), finish-to-start arrows, legend, Days/Weeks zoom (weeks for long plans and phones), today line for IN_PROGRESS/ON_HOLD/REVIEW_WINDOW, names in an HTML column wrapped to two lines, a live details line on hover/focus/tap. Dependency graph names wrap to two lines; nodes are focus stops (axe `scrollable-region-focusable` once the graph scrolls). 15 new unit tests; 6 plan-page visual baselines regenerated.
- The gate's secret scanners caught a GitHub token file in the working tree (`ptoken.txt`, untracked); moved out of the repo. One gate run lost step 13 to memory pressure (Chrome open); the isolated test passed 6/6 and the rerun passed.
- Seen but not changed: WebKit/mobile axe colour-contrast checks occasionally fire mid fade-in on the developer home and homepage glow (not part of the gate, which runs axe on Chromium).

### 2026-10-22 — Taeen (with Claude Code), Phase 5 merged; follow-ups
- Merged `phase-5` into `main` (fast-forward) and tagged `phase-5`; `make demo-check DEMO=1` exposed that the seeded demo accounts (`@devsync.local`) could not sign in and that the walkthrough expected screens it never reached.
- Built every item of the external Phase 5 review on `phase-5-followups` (D54, security review findings 6–8) with property, API, job, perf, unit and cross-browser E2E tests and visual baselines for the bidding screens.
- `make demo-check DEMO=1` passed on the branch (gate PASS + walkthrough 12/12) once the laptop had free memory (an earlier run lost step 12 to swap exhaustion with Chrome open); merged into `main` (fast-forward), `phase-5` tag moved to the merge.
- Found and fixed on the way: the bundled breached-password list was never committed (`data/` ignore rule); the client view read ORM rows after its SYSTEM session closed (500); the shared dialog close button shrank on phones; `demo-check` left the test stack unseeded when the gate stopped early.

### 2026-10-21 — Taeen (with Claude Code), Phase 5 review and gate
- Reviewed Salwa's Phase 5 and ran the gate until `PHASE 5 GATE: PASS` (run 9 of the day; runs 4–6 were cut short by a battery that would not charge).
- Real defects fixed: vulnerable Pillow/certifi (D51); `/projects/{id}` shadowing search routes, query bounds, float-free ordering (D52); WebKit could send an empty CSRF header after `GET /auth/csrf` (token now echoed in a header); sign-up's automatic sign-in now solves the CAPTCHA when asked; NUL/control characters in search → 500 (now cleaned, skill filters capped at 20); sign-out does a full page load; hero headline accessible name; 44 px touch targets (D53, security review findings 3–5).
- E2E robustness: viewport-aware helpers, smooth scrolling off in tests, homepage link tests on reduced motion (software WebGL in the container), gitleaks skips Playwright output.
- Not merged or tagged; follow-ups recorded under Known issues.

### 2026-10-20 — Salwa (with Claude Code), Phase 5 build
- **Done:** approved `docs/plans/phase-05.md`; built Phase 5 end to end on `phase-5`. Backend —
  migration 0006 (bids/reservations/reputation_snapshots + project search, sealed-bid RLS, SYSTEM
  eligibility policies D50); pure `filtering.py` (Algorithm 1 + newcomer rule + relaxation +
  shortlist), `reputation.py` (newcomer_snapshot), `availability.py`; `reputation_read`; marketplace
  + bids services and 12 routes; authz matrix; bidding-deadline job; stage-1 seed + `phase5_checks`.
  Frontend — Find Projects, bid sheet with live eligibility, My Bids, client Bids + too-few banner.
- **Tests:** 35 algorithm (99%), ~60 backend in the stack (bids API, RLS bids/projects, authz
  matrix, jobs, seed self-assertion), 278 frontend (≥70% all metrics). Decisions D44–D50; security
  review phase-05 (0 unresolved high).
- **Next:** `phase5.spec.ts` + Demo-1 tooling + visual baselines, then the full gate.

### 2026-10-20 — Salwa (with Claude Code), Phase 4 merge
- **Done:** reviewed Taeen's Phase 4 fixes (DECISIONS D43) and agreed with all of them — several
  fixed real defects in the original frontend (the `"preview"` placeholder id, GET hooks on
  endpoints that don't exist, missing payment-verify UI, plan-graph edges). Re-verified on this
  laptop: `tsc -b`, eslint, prettier, vitest (269), backend `pytest -m "unit or api"` (347;
  stack-only tests skipped here, green on Taeen's gate), DB at `0005`. Skipped the full-stack
  `phase4.spec.ts` locally (2.6 GB free → D28 flake risk; already PASS on Taeen's gate).
- **Merged** `phase-4` into `main` (ff-only) and **tagged `phase-4`** at `5b4edc5`.
- **Next:** Phase 5 in Plan Mode.

### 2026-10-20 — Taeen (with Claude Code), Phase 4 review
- **Done:** pulled `phase-4`; ran the gate (PASS as delivered on this laptop); reviewed against
  the spec and wrote the missing Phase 4 E2E, which exposed broken wizard saves, impossible
  publishing, no loop demo, a plan graph without edges, and missing spec items — all fixed (D43),
  with unit/API/E2E tests and visual baselines for the planning screens. Gate PASS.
- **Next:** Salwa merges and tags `phase-4`, then Phase 5.

### 2026-10-19 — Salwa (with Claude Code), Phase 4
- **Done (backend, earlier in the day):** pure CPM + forecast algorithms (`app/algorithms/`,
  §18.2 golden verified, 300-milestone CPM < 50 ms); migration `0005` (7 tables, FORCE RLS,
  `is_project_client`/`project_visible` definers, baseline-immutability + publish-guard triggers);
  project schemas/repository/service (draft CRUD, whole-set slot/milestone/dependency replace,
  CPM-cycle → 422, publish §8 guards, extend-bidding cap, cancel, payment-verify D39); 14 routes
  with OpenAPI examples; authz policies + matrix rows; 34 backend + 35 algorithm tests; ERD
  generator (`make erd`) and `phase4_checks`. Decisions D38–D42.
- **Done (frontend, this session):** regenerated `schema.d.ts`; `features/projects/api.ts` (15
  TanStack Query hooks); custom-SVG `Gantt`, `DependencyGraph`, `CpmTable` (critical path in rose,
  slack, today/deadline lines, keyboard-focusable, table alternative); 6-step create-project
  wizard with live CPM preview and D40 schedule-risk acknowledgement; plan page; My Projects +
  reason-collecting cancel dialog; `TagPicker`; routes/nav wired (`phase:4` flags dropped); new
  client screens registered in `e2e/screens.ts`. Added a `headers` option to the API client for
  `If-Match`. 267 frontend tests pass; coverage ≥70% on all four metrics; lint/types/build green.
- **Security review:** `docs/security-reviews/phase-04.md`, 0 unresolved high, no fixes needed
  (new surface reused the Phase 1–3 authz/RLS/schema patterns).
- **Next:** run `make gate PHASE=4` with the Docker stack up (regenerate visual baselines for the
  two new client screens if the visual step flags them), then commit/tag `phase-4` for the user to
  push.

### 2026-10-18 — Taeen (with Claude Code), Phase 3
- **Done:** Phase 3 plan approved (`docs/plans/phase-03.md`); migration 0004 (profiles, skills,
  files, portfolio, certificates, external reviews, question bank, timed attempts, skill
  evidence) with RLS, guard triggers and SECURITY DEFINER test functions; 8 skills and 128 seeded
  questions; upload pipeline (`app/uploads/`: signatures, polyglot/PDF checks, Pillow re-encode
  without EXIF/GPS, signed 5-minute links, Nginx `X-Accel-Redirect`); profile, portfolio,
  evidence, file and skill-test APIs; orphan-file cleanup and expired-attempt jobs; screens:
  Profile & portfolio (autosave, drag reorder, dropzone), Skill challenges, timed test, public
  profile `/d/:id`, client organisation in Settings; real dashboard checklist.
- **Security review:** `docs/security-reviews/phase-03.md`, 0 unresolved high, 6 findings fixed
  (definer `is_system()` pitfall, self-verification guard, unverified clients, PDF escapes,
  parallel starts, upload volume permissions).
- **Also fixed:** sign-out race (guard redirected to /login before navigating home), visibility
  PATCH 500, autosave retry loop, coverage measurement under greenlets. Decisions D29–D37.
- **Gate:** first run failed on lint/types in a script; second run PASS.
- **Next:** hand-off for Phases 4–5; question-bank review by a team member.

### 2026-10-17 — Taeen (with Claude Code), Phase 2
- **Done:** Phase 2 plan approved (`docs/plans/phase-02.md`); design tokens (light/dark), theme
  and reduced-motion providers, motion system + lint rule; component library on Radix; role
  shells (sidebar, tab bar, command palette, toasts, offline/error/coming-soon pages); homepage
  per §13.11 with the 3D talent constellation (slim three entry, poster first, fallbacks),
  stills and social preview; auth screens restyled with password rules up front;
  `/public/stats`, `/client-errors`, migration 0003; `devsync-ui` skill; UI kit (dev only).
- **Security review:** `docs/security-reviews/phase-02.md`, 0 unresolved high, 5 findings fixed
  (Zod eval under CSP, Radix styles via a per-response nonce, `.dockerignore` keeping `.env` out
  of build contexts, …).
- **Gate:** several passes. Performance work from Lighthouse (desktop 78 → 97, mobile 60 → 96),
  responsive-matrix fixes, the 60 fps check moved to the laptop GPU. Decisions D21–D28.
- **Next:** manual testing of Phases 0–2 by the student; then Phase 3 in Plan Mode.
- **Blockers:** none.
### 2026-10-17 — Taeen (with Claude Code), Phase 1
- **Done:** Phase 1 plan approved (`docs/plans/phase-01.md`); migration 0002 (identity tables,
  RLS ENABLE+FORCE on every table, SECURITY DEFINER pre-auth functions, settings v2 with rate
  limits); Argon2id + breached list + zxcvbn; rotating server-side sessions; CSRF; Redis rate
  limits; ALTCHA CAPTCHA + honeypot + fill time; lockout; admin TOTP, recovery codes, step-up;
  deny-by-default authz with route × role matrix; outbox email + lifecycle jobs; frontend auth
  screens (login, admin TOTP, register, verify, forgot/reset, settings, role homes) with guards.
- **Security review:** `docs/security-reviews/phase-01.md`, 0 unresolved high, 7 findings fixed.
- **Gate:** three passes. Fixes: narrower semgrep rule, timing test with interleaved medians,
  typographic apostrophes in UI copy, forms wait out the 2 s minimum fill time instead of
  failing (fast password-manager users), smoke test ignores the expected anonymous `/me` 401.
  DECISIONS D19–D20.
- **Next:** Phase 2 in Plan Mode.
- **Blockers:** none.
### 2026-10-17 — Taeen (with Claude Code)
- **Done:** repository cloned; spec, paper and proposal studied; Phase 0 plan approved
  (`docs/plans/phase-00.md`); backend core (config, logging, errors, middleware, health,
  metrics, money, clock), migration 0001 (settings, hash-chained append-only audit log,
  jobs, idempotency keys), platform settings schema/service, RQ worker + scheduler, gate and
  checker scripts, Nginx/Compose/Postgres roles, frontend scaffold with tokens, docs, CI.
- **Gate:** four passes; fixes recorded in DECISIONS D15–D18 (frontend toolchain CVEs, Nginx
  host allowlist, SHA-pinned actions, Trivy DB source, Nginx 1.30/trixie base). Docker moved
  from the snap to Docker's apt packages (D17). Design skills installed after review (D14).
- **Next:** Phase 1 in Plan Mode.
- **Blockers:** none.
