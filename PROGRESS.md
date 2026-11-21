# DevSync progress

## Current state
- **Current owner:** Raisa Tabassum (frontend developer), Phases 6–7, from 2026-11-21 (hand-off from Taeen: `docs/handoffs/handoff-02-taeen-to-raisa.md`; paste-in prompt `docs/handoffs/handoff-02-start-prompt.md`).
- **Current phase:** 6 (reputation engine and market simulator), built on branch `phase-6`; **gate not run yet**. Plan `docs/plans/phase-06.md` (approved 2026-11-21), decisions D83–D101, security review `docs/security-reviews/phase-06.md` (0 unresolved high). `main` = `origin/main` = `c9e5d71` (hand-off 02).
- **Last gate result:** none for Phase 6. Phase 5's last full PASS is 2026-10-29; on 2026-11-20 steps 1–12 passed on the final Phase 5 code (details in the hand-off).
- **Verified on Raisa's laptop (WSL 2, 2026-11-21):** backend suite on the Phase 6 code: everything passes except `tests/security/test_rate_limits.py::test_admin_limit_is_per_user` under full-suite load (see Known issues); algorithms + property 292, API/engine/RLS/job 49, frontend 525, Phase 6 E2E 3/3, stage-1 and stage-2 seeds, `alembic` upgrade/downgrade/check, OpenAPI contract 0 problems.
- **In progress:** visual baselines for the two new screens (`make visual-update`), then the full gate.
- **Very next step:** run `make gate PHASE=6` **on a native Linux laptop with an Intel/AMD GPU** (gate step 16 cannot pass on WSL 2, see Known issues), then update this file, commit `phase-6: …`, merge to `main`, tag `phase-6`, push. Then the Phase 7 plan.
- **Open human tasks:** review the 128 drafted test questions (D34); tester's human check of the Phase 3, 4 and 5 security reviews; sanity-check D39 (simulated payment-method verification).

## Phase table
| Phase | Owner | Status | Gate | Date | Tag |
|---|---|---|---|---|---|
| 0 Foundations | Taeen | done | PASS | 2026-10-17 | phase-0 |
| 1 Accounts & security core | Taeen | done | PASS | 2026-10-17 | phase-1 |
| 2 Design system & landing | Taeen | done | PASS | 2026-10-17 | phase-2 |
| 3 Profiles & skill tests | Taeen | done | PASS | 2026-10-18 | phase-3 |
| 4 Projects & CPM | Salwa (review fixes: Taeen) | done | PASS | 2026-10-20 | phase-4 |
| 5 Marketplace & filtering | Salwa (gate fixes: Taeen) | done | PASS | 2026-10-21 | phase-5 |
| 6 Reputation & simulator | Raisa | built, gate pending | — | — | — |
| 7–15 | — | not started | — | — | — |

## Gate log (newest first, appended by `make gate`)
| Finished (UTC) | Phase | Result | Tests |
|---|---|---|---|
<!-- gate-log -->
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
- The full gate needs about 3 GB of free memory (7 GB laptop): close Chrome first. Under swap pressure WebKit E2E runs time out, and those failures say nothing about the code.

- **Gate step 16 can't pass on WSL 2 (checked 2026-11-21).** `/dev/dri/renderD128` exists under WSLg, but inside the GPU Playwright image Chromium falls back to `llvmpipe` (software), and the `@perf|@gpu` tests correctly refuse it (5 failed). The real GPU is reached through `/dev/dxg` (Direct3D 12); the image has no Vulkan-on-D3D12 driver. Run the gate on a native Linux laptop (D28), or decide (with Taeen) whether to extend the GPU image for WSL.
- **`test_admin_limit_is_per_user` is timing-sensitive on slow machines.** It sends 300 admin requests that must all land inside a 60-second window. Alone on this WSL laptop it passes 3/3 but takes 52–54 s; under the full suite it went over and failed. Not a Phase 6 change; not modified. Watch it in the gate on a faster machine; if it fails there too, fix the test's timing at the cause (not by loosening the limit).

## Session log (newest first)
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
