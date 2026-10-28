# Role Assessment for Newcomers — plan

Source: `ROLE_ASSESSMENT_BUILD_SPEC.md` (wins over the build spec for this feature only; each
conflict is recorded in `DECISIONS.md`). Branch `role-assessment`, created from `main` at
`c794d51` (= `wizard-drafts`, the certified Demo 1 build).

## Context
Newcomers get past Algorithm 1 today with a generic 10-question skill test that the bid never
checks; the score is just the best TEST evidence for the skill. The feature replaces that with a
**role assessment per project slot**: a rule-based blueprint built from the project's own data,
the same for every newcomer bidding for that slot, scored with difficulty weights and a
per-competency floor, taken in focus mode with server-enforced one-way navigation. Generic tests
become practice. Target: Demo 1 (Mon 2 Nov); merge only if the gate, the security review and
`make demo-check DEMO=1` all pass by Sun 1 Nov (spec §0.5), otherwise it stays on this branch.

## What exists and is reused (verified in the code)
- **Test engine** — migration 0004: definers `start_test_attempt`, `attempt_questions`,
  `record_test_answer`, `score_test_attempt`, `caller_is_system()`, the `DEFINER_NAMES`
  REVOKE/GRANT loop, per-user advisory lock (`hashtextextended`), RLS `owner_select` only (writes
  only through definers). Service `app/services/skill_tests.py` (SQLSTATE → `DomainError` map,
  `_state_error` with `allowed_actions`), repo `app/repositories/skill_tests.py`
  (`select(column(...)).select_from(func.fn(...))`), API `app/api/v1/skill_tests.py`, expiry job
  `app/jobs/profile_jobs.py` + `scheduler.py` (`attempts.expire`, every minute).
- **Bank** — `scripts/build_question_bank.py` (128 questions in Python) →
  `alembic/seed/skills_and_questions_v1.json`, loaded by 0004. Answers spread across A–D.
- **Settings** — new group in `app/schemas/platform_settings.py` + frozen
  `platform_settings_v5.json` + `bulk_insert` in the migration (the 0009 pattern; tests require
  the newest seed to equal the defaults).
- **Bidding** — `algorithms/filtering.py` (`classify_bid`: `NO_SKILL_EVIDENCE` when newcomer and
  `skill_evidence_score < pass_mark`, devsync mode only; relaxation never touches it),
  `services/bids.py` (`create_bid`, `update_bid` slot change, `_bidder_data` →
  `best_evidence_by_developer`, `_dry_run` preview, `_DEV_REASON` / `_check_out` texts,
  `_client_rows` `newcomer_evidence`), `record_evaluation` at close, `reputation_read`
  (`is_newcomer`, `_evidence_domains`), `services/notifications.py` (`notify_users`).
- **Publish** — `services/projects.py` `publish` (one transaction; slot links are created here).
  After publish, slots are never added or removed (`bidding_terms` only lowers counts), so links
  are only created at publish.
- **Admin** — `require("admin.access")`; step-up is an inline `principal.has_step_up(now)` check
  in the service (`STEP_UP_REQUIRED`). The admin frontend has only a shell, home and 2FA setup.
- **Frontend** — `features/challenges/{ChallengesPage,TestPage}.tsx`,
  `features/marketplace/ProjectBidPage.tsx`, `features/bids/{BidExplanation,ClientBidsPage,
  bidText}.ts(x)`, `lib/storage.ts` (localStorage prefs only; no sessionStorage helper yet),
  `lib/inlineCode.tsx`. Playwright projects chromium / firefox / webkit / mobile (iPhone 14).
- **Demo** — `scripts/seed_demo.py` (`NEWCOMERS`, `BIDS`, `_assert_filter` = 10 eligible +
  TOO_SLOW + NO_SKILL_EVIDENCE), `demo_check.py`, `e2e/demos/demo-1.spec.ts` (step 5 uses the
  TEST-only `/__test__/attempts/{id}/answer-key` route).
- **Permissions-Policy** (`infra/nginx/*.conf`) doesn't restrict `fullscreen`, so nothing to
  change; a test will pin that.

## Conflicts and decisions (D71–D88 in `DECISIONS.md`)
The spec's 16 decisions (§3) are recorded as written. In addition:
1. **Migration number** — the spec's example is `0007`; the next free number is **`0011_role_assessment`**.
2. **Grace period** — the spec's 5 s grace after the deadline is new; practice tests keep their current rule (no grace).
3. **`_demo` database for the answer key** — the demo stack's database is currently `devsync`. The demo overlay gets its own database **`devsync_demo`** on its own volume (`pgdata_demo`; the DB name is parameterised in compose and the URLs). Side effect: `make up` (development) and the demo stack stop sharing data. That's cleaner, but the first `make demo-up` starts from an empty database (it migrates and seeds anyway).
4. **Playwright and the answer key** — the Playwright container has no database access and no Python, so it can't spawn the CLI script. The E2E tests on the TEST stack use a TEST-only route `/__test__/assessment-attempts/{id}/answer-key`, guarded exactly like the existing one (mounted only when `DEVSYNC_ENV=test`, `assert_no_test_routes`). Both the route and the CLI call the **same** function, and the CLI is tested separately: refusals, watch and output.
5. **Bid creation becomes a gate.** Today a newcomer can place a bid that is only filtered later. Spec §8.3 makes it `409 ROLE_ASSESSMENT_REQUIRED` at create time and on a slot change.
6. **Idempotency** — `app/core/idempotency.py` exists but no route used it yet; the start route is its first user.
7. **Bank format** — YAML per skill under `scripts/seed_data/question_bank/` (PyYAML is already a locked runtime dependency, no new dependency). `build_question_bank.py` keeps the 0004 seed byte-identical, so the old migration doesn't change; the new content goes into a new frozen seed loaded by 0011.

## Build steps (spec §19 order; each step keeps the gate green)
1. **Migration 0011 + models + settings + RLS**: everything in spec §4.
   - New enums: `question_status`, `question_source`, `review_level`, `attempt_kind`, `terminated_reason`, `blueprint_status`.
   - `ALTER TYPE evidence_source ADD VALUE 'ROLE_ASSESSMENT'`. This is the first enum change in the repo: it runs outside the transaction block via `autocommit_block`, and the downgrade deletes those rows and recreates the type.
   - Immutability triggers for approved questions and for blueprints.
   - New indexes, plus `user_accommodations` and the `bids.assessment_evidence_id` column.
   - `assessment` settings group in `platform_settings_v5.json`; new rate-limit scopes.
   - Every new table gets ENABLE + FORCE RLS; `check_rls.py` must stay green.
2. **Question bank, written and self-verified by me** (§13).
   - Competency catalogue with keywords for all 8 skills; the 128 existing questions tagged, each with an explanation.
   - New questions so that React, FastAPI, PostgreSQL and Testing have **≥ 2 easy, 2 medium and 2 hard approved questions per competency** (≈ 40 per skill, ~110–130 new). The other four skills get ≥ 4 per core competency from the existing questions plus a few new ones; any shortfall uses the practice fallback (Decision 10).
   - **Execution checks** under `scripts/question_checks/` (`make question-checks`): Python with the project's Python, JS with Node, SQL against the test Postgres. Every code question proves the right option is right and each distractor is wrong.
   - An **independent second solve** of every question by fresh subagents that never see the answer. They also check for a second defensible option and rate the difficulty. Results are recorded in `verification`.
   - Questions that fail get rewritten or dropped; failures stay `DRAFT`.
   - Builder validation: duplicates/near-duplicates, A–D balance, per-competency counts.
   - `docs/question-review/verification-report.md`, plus the team review files for each skill and `make question-approve` (§13.3).
3. **Pure algorithms** (`app/algorithms/role_blueprint.py`, `assessment_selection.py`, `assessment_scoring.py`), with unit and hypothesis tests (§17.1–17.2) and ≥ 30 shared scoring vectors.
4. **Definer functions** (§10) with integration tests.
   - Concurrency: two starts, two answers, focus events.
   - Token, deadline and grace; idempotent scoring; one evidence row per attempt; `times_served`.
   - Triggers, RLS cross-user checks, migration up/down.
   - SQL ↔ Python scoring parity on the shared vectors.
5. **Contract first**, then services and API (§6, §8.1, §9), with every error code in `ErrorCode`.
   - Status endpoint, start (idempotent), resume, get, answer, finish, focus-events, heartbeat, result, and `/me/role-assessments`.
   - Expiry job extended to role attempts.
   - Authz matrix rows, IDOR, rate limits, CSRF, a scan proving no answer data leaves, schemathesis.
6. **Integration with bidding** (§8.2–8.5).
   - Blueprints are created inside `publish`.
   - `NewcomerEvidence.assessment_passed` drives the newcomer check.
   - `_bidder_data` builds per-slot evidence (role result for the blueprint's fingerprint, or the practice fallback).
   - Create and slot-change enforce the gate and link `assessment_evidence_id`; eligibility of existing bids uses the linked evidence.
   - New reason texts; the preview includes the assessment status; the client line in the bid explanation.
   - Void → re-evaluation and a notification. `evidence_domains` counts valid passes.
   - All existing filtering and bids tests stay green.
7. **Frontend** (`features/assessment/`, §11), loading `devsync-ui` + `frontend-design` first.
   - Bid sheet: `AssessmentStatusCard` in every status, plus `useBidDraft` through a new allowlisted sessionStorage helper that is cleared on submit and on logout.
   - Consent dialog; full-screen runner with one-way navigation, skip and finish early, and keys 1–4 + Enter.
   - Countdown from the server offset (`useServerClock`); `useFocusGuard` (debounce, coalescing, keepalive and pending leaves, heartbeat).
   - Warning overlay; terminated, moved and expired screens; `ResultView`.
   - Practice tests renamed; profile section.
   - Unit, a11y and visual tests in light/dark at 390/1440.
8. **Admin tools** (§12).
   - Flagged queue and detail, with void (step-up) and mark reviewed.
   - Accommodations (step-up).
   - Question-bank review: list, approve, retire.
9. **Seed and demo** (§14).
   - Stage-1 seed: blueprints at publish; Nadia and Mehjabin passed; Lamia failed at 52 (§18.4 counts unchanged); new newcomer **Rafsan Haque**; one flagged terminated attempt.
   - `make demo-answer-key USER=rafsan` CLI (`DEVSYNC_DEMO_TOOLS=1`, `_demo` database, migrator credentials, `--watch`).
   - Walkthrough steps added; E2E §17.6 scenarios 1–13.
10. **Finish**:
    - `make gate PHASE=5`, `/security-review` → `docs/security-reviews/role-assessment.md`, `make demo-check DEMO=1`.
    - Docs (§18): `docs/ROLE_ASSESSMENT.md`, ALGORITHMS, user guides, FR mapping, PROGRESS.
    - An honest report.

## Time and cut lines
There are about 3½ days to Sunday's merge deadline. The full gate takes about 1½ hours and `demo-check` about 2½ hours, so the last full certification must **start by Sunday morning**.
- If time runs short, the spec allows moving these after Demo 1: **admin question-review UI (§12.2)**, **accommodations (§12.3)**, and the banks of the four non-demo skills (their slots use the practice fallback).
- Never cut: server rules, focus mode, scoring parity, the E2E walkthrough.
- If the certification can't pass by Sunday, the feature stays on `role-assessment` and Demo 1 uses the current `main`, as the spec's merge rule says.

## Verification
- Unit, property, integration (DB), API/security, frontend and E2E suites (§17), all run through `make gate PHASE=5`: no thresholds lowered, no tests removed.
- `make question-checks` passes, and the verification report shows every approved question verified.
- `make demo-check DEMO=1`: the walkthrough including Rafsan's live assessment on 4 browsers × 3.
- Manual check on the demo stack: Rafsan takes the assessment with the answer-key CLI on a second terminal, bids, and the client sees the assessment line. Leaving twice ends an attempt, and the admin can void it.
