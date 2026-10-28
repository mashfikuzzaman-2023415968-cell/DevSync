# DevSync — Role Assessment for Newcomers: Complete Build Specification

**Audience:** Claude Code, working in the existing DevSync repository.
**Goal:** replace the newcomer evidence used for bidding (generic skill tests) with a **role-specific assessment** that every newcomer bidding for the same role takes under the same rules, so the result is fair, comparable and defendable. Finish it as part of the Phase 0–5 scope for **Demo 1 (Monday 2 November 2026)**, fully tested end to end.

This document is self-contained. Together with `DEVSYNC_BUILD_SPEC.md` and `CLAUDE.md`, it is everything needed. Where they conflict, this document wins **for this feature only**, and each conflict is recorded in `DECISIONS.md`.

---

## Contents

0. How to work on this
1. Concept and principles
2. What already exists (reuse it)
3. Decisions to record
4. Data model
5. Algorithms
6. Attempt lifecycle and rules
7. Focus mode and the two-leave rule
8. Integration with bidding and Algorithm 1
9. API contract
10. Database functions and security
11. Frontend
12. Admin tools
13. Question bank content
14. Seed data and the Demo 1 walkthrough
15. Security checklist for this feature
16. Corner cases (all must be handled and tested)
17. Tests
18. Documentation
19. Implementation order
20. Definition of done

---

## 0. How to work on this

1. **Branch safety first.** Run `git status`, `git branch -a` and `git log --oneline -15`. Identify the branch with the latest Demo 1 work (the readiness check passed on `wizard-drafts`; verify whether it has been merged into `main`). Never reset, clean, stash-drop or overwrite anyone's work. Create `role-assessment` from the branch that contains the latest Demo 1 work.
2. **Plan Mode.** Read this whole file plus `DEVSYNC_BUILD_SPEC.md` §0, §7, §9.1.3, §9.2, §10, §13, §14, §16, §17.0, §18.4, and the latest `PROGRESS.md`, hand-off document and `DECISIONS.md`. Write the plan to `docs/plans/role-assessment.md` and wait for approval.
3. **Load skills** `devsync-ui` and `frontend-design` before any frontend work (spec §0.4).
4. **Contract-first API** (spec §10.4): write and commit schemas and examples before implementing routes.
5. **Merge rule.** Merge into the Demo 1 branch **only if** the full gate (`make gate PHASE=5`), the security review and `make demo-check DEMO=1` all pass **by Sunday 1 November 2026**. Otherwise leave it on its branch and tell the student clearly; Demo 1 is presented with the existing version.
6. **Honest reporting.** At the end, report exactly what was built, which tests ran and their results, and what's left. Never claim something passed that didn't run.

---

## 1. Concept and principles

**Problem.** The PCS model needs past projects; a developer with none can't be judged, and Algorithm 1 would filter them out. DevSync's newcomer rule (spec §9.2) replaces the performance check with skill evidence. Generic skill tests are easy to question ("why does a React quiz prove you can do *this* job?").

**Solution: Role Assessment.** When a newcomer wants to bid for a role (a project **slot**), they take an assessment built from a **blueprint** of that role's competencies, derived from the project's own data.

**Principles (non-negotiable):**
1. **Per role, not per person.** A blueprint depends only on the project and slot, never on the candidate. Every newcomer bidding for that slot faces the same competencies, weights, question count, difficulty mix, time limit and pass rule.
2. **No live AI.** Questions come only from the **approved** question bank (self-verified for Demo 1, human-approved afterwards; §13.3). Nothing is generated during an assessment.
3. **Evidence, not reputation.** A result is competency evidence. It never creates completed projects, reviews, punctuality, re-employment or teamwork data.
4. **Only real work ends newcomer status.** Newcomer status is unchanged: fewer than `newcomer.threshold` (3) completed projects. A passed assessment never changes it.
5. **Algorithm 1 stays in charge.** A pass satisfies only the newcomer evidence check. Deadline, budget, skill, availability, suspension and self-dealing checks still apply. `pcs_replication` mode is unaffected (it has no newcomer rule).
6. **General skill tests become practice.** They stay available and keep showing on profiles, but no longer count for the newcomer rule.

---

## 2. What already exists (reuse it; verify every item in the code)

| Area | Location | Notes |
|---|---|---|
| Skills | `skills` table, 8 seeded skills with domains | React, Node.js, FastAPI, PostgreSQL, UI/UX, Testing, Flutter, DevOps |
| Question bank | `question_bank` (text, 4 options, `correct_index`, `difficulty` 1–3, `active`), built by `backend/scripts/build_question_bank.py`, 128 questions (16 per skill) | Correct answers never leave the database |
| Tests and attempts | `skill_tests`, `test_attempts`; DB functions `start_test_attempt`, `attempt_questions`, `record_test_answer`, `score_test_attempt` (migration `0004_profiles_files_tests.py`, `SECURITY DEFINER`, advisory locks, server deadline) | Service `app/services/skill_tests.py`, repo `app/repositories/skill_tests.py`, API `app/api/v1/skill_tests.py` (`/skill-tests`, `/skill-tests/{id}/attempts`, `/attempts/{id}`, `/attempts/{id}/answer`, `/attempts/{id}/submit`), expiry job `score_expired_attempts` |
| Evidence | `skill_evidence` (`user_id`, `skill_id`, `source` enum `evidence_source` = TEST, CODING, ADMIN_PORTFOLIO, `score` 0–1, `attempt_id`, `at`) | Read by `best_evidence_by_developer` in the bids repository |
| Projects | `projects`, `project_slots` (`skill_id`, `label`, `count`), `milestones`, `milestone_skills`, `milestone_dependencies` (migration `0005`) | Publishing moves DRAFT → BIDDING |
| Filtering | `app/algorithms/filtering.py` (`NewcomerEvidence`, `newcomer_pass_mark = 0.60`, reason `NO_SKILL_EVIDENCE`), `app/services/bids.py` (builds inputs, explanations, eligibility preview `POST /projects/{id}/bids/eligibility`) | Newcomer rule only in `devsync` mode |
| Reputation | `app/algorithms/reputation.py` (`newcomer_snapshot`, `evidence_domains`), `app/services/reputation_read.py` | Starting Expertise = 0.2 × domains with evidence ≥ pass mark (max 0.5) |
| Frontend | `features/challenges/ChallengesPage.tsx`, `TestPage.tsx`; `features/marketplace/ProjectBidPage.tsx`; `features/bids/*` (incl. `BidExplanation.tsx`, `ClientBidsPage.tsx`) | |
| Demo | `backend/scripts/seed_demo.py` (Nadia React 0.85 TEST evidence), `seed_data/stage1_reputation.json`, `frontend/e2e/demos/demo-1.spec.ts`, `make demo-check DEMO=1` | Build spec §18.4 expected counts: 10 eligible; Shakib TOO_SLOW; Lamia NO_SKILL_EVIDENCE |

**Reuse rule:** follow the existing patterns exactly (definer functions with pinned `search_path`, caller checks, `REVOKE ... FROM PUBLIC`, advisory locks, audit actions, error codes, response envelopes, TanStack Query hooks, shared UI components). Do not create a second, parallel test engine.

---

## 3. Decisions to record in `DECISIONS.md` (next free D-numbers)

1. Role Assessment replaces generic tests as the newcomer evidence for bidding; general tests become **practice** (still shown on profiles as "practice result").
2. Blueprints are **per project slot**, deterministic, rule-based, versioned (`BLUEPRINT_ALGO_VERSION = 1`); frozen when bidding opens.
3. Results are reusable for any slot with the **same blueprint fingerprint** for **180 days**.
4. Retake: one scored attempt per fingerprint per **30 days**; at most **one open attempt** per user across practice tests and role assessments.
5. Pass rule: overall ≥ **60%** **and** every competency with weight ≥ **20%** scores ≥ **40%**.
6. Scoring weights by difficulty: easy 2, medium 3, hard 4 (integer form of 1 / 1.5 / 2).
7. **One-way navigation:** one question at a time, answered questions locked, no going back. **No per-question timers;** one overall timer (default **15 minutes** for 12 questions).
8. **Focus mode and two-leave rule** (§7): first leave = warning; second leave = attempt ends, scored, **cannot pass**, flagged for admin. Signals come only from the assessment page and are disclosed beforehand; no camera, screen or keystroke recording.
9. Terminated attempts count toward the retake limit.
10. If a blueprint can't be built from approved questions (bank too small), the slot falls back to the **practice test of the slot's skill** as newcomer evidence, and the UI says so (prevents dead ends).
11. Bids from newcomers without a valid passing result are **rejected at creation** (`409 ROLE_ASSESSMENT_REQUIRED`). Each newcomer bid stores the evidence id used.
12. No LLM at runtime in this feature. Future LLM use is limited to an admin drafting tool (drafts need human approval).
13. Bid drafts are kept in memory and `sessionStorage` (non-sensitive text only, cleared on submit or logout), through the allowlisted storage helper.
14. **Question review for Demo 1:** because of time, Claude Code writes **and verifies** the question bank itself (§13.3). Questions it has verified are usable with `review_level = SELF_VERIFIED`. **Human review by the team happens after Demo 1** and upgrades questions to `HUMAN_APPROVED`; a setting (`assessment.require_human_review`, default `false` until then) will later restrict assessments to human-approved questions only. This is stated openly in the documentation and the viva notes.
15. New role-assessment questions are **not** used by practice tests (`active = false`), so practice tests don't reveal the role-assessment pool; the original 128 questions remain the practice pool.
16. Display times in `Asia/Dhaka`; store UTC.

---

## 4. Data model (one new migration, e.g. `0007_role_assessment.py`, with a working downgrade)

### 4.1 `competencies` (new)
| Column | Type | Rules |
|---|---|---|
| `id` | uuid PK | |
| `skill_id` | uuid FK skills | |
| `code` | text | unique per skill, `^[a-z][a-z0-9_]{2,40}$` |
| `name` | text | 3–60 chars, shown to users |
| `description` | text | ≤ 300 chars |
| `is_core` | bool | core competencies of the skill |
| `keywords` | text[] | lowercase, 1–40 items, each 2–40 chars; used for requirement matching |
| `position` | smallint | display order |
| `active` | bool default true | |

RLS: readable by all signed-in users and guests (no secrets); writable by admins only.

### 4.2 `question_bank` (extend)
Add:
| Column | Type | Rules |
|---|---|---|
| `competency_id` | uuid FK competencies, nullable | **required** when `status = APPROVED` (CHECK) |
| `status` | enum `question_status` (`DRAFT`, `APPROVED`, `RETIRED`) | default `DRAFT`; existing rows become `APPROVED` after tagging (§13) |
| `source` | enum (`HUMAN`, `CLAUDE_GENERATED`) | default `HUMAN`; new questions written by Claude Code use `CLAUDE_GENERATED` |
| `code_snippet` | text, nullable | ≤ 1,500 chars, plain text only, rendered as a monospace block; never HTML |
| `explanation` | text, nullable | ≤ 600 chars, for admins (not shown to candidates in this version) |
| `review_level` | enum (`NONE`, `SELF_VERIFIED`, `HUMAN_APPROVED`) | default `NONE`; `APPROVED` requires `SELF_VERIFIED` or `HUMAN_APPROVED` (CHECK) |
| `reviewed_by_name` | text, nullable | name of the team member who approved (required when `HUMAN_APPROVED`; team members don't need platform accounts) |
| `reviewed_by_user` | uuid FK users, nullable | set when an admin approves through the admin screen |
| `reviewed_at` | timestamptz, nullable | set when `SELF_VERIFIED` (verification time) or `HUMAN_APPROVED` |
| `verification` | jsonb, nullable | self-verification record: `{method: "execution" | "independent_solve", checks_passed, solver_agreement, verified_at}` |
| `times_served` | integer default 0 | exposure count (updated by DB functions) |
| `version` | integer default 1 | increment on any content change |

Rules:
- A trigger makes the **content** of an APPROVED question immutable: `text`, `options`, `correct_index`, `code_snippet`, `competency_id`, `difficulty`. Allowed updates on approved rows: review fields (`review_level`, `reviewed_by_name`, `reviewed_by_user`, `reviewed_at`, `verification`), `times_served`, and `status` APPROVED → RETIRED. A correction means: retire the old row and insert a new row (new id, `version + 1`, `status DRAFT`).
- `active` remains the practice-test flag. Existing 128 questions keep `active = true`; new questions get `active = false` (Decision 15). Role assessments use `status = APPROVED` only, filtered by review level (§5.4).
- Retiring a question must never leave a practice test with fewer active questions than its `question_count` (the builder and the retire action check this).

### 4.3 `assessment_blueprints` (new)
| Column | Type | Rules |
|---|---|---|
| `id` | uuid PK | |
| `algo_version` | smallint | = `BLUEPRINT_ALGO_VERSION` |
| `fingerprint` | char(64) | SHA-256 hex; unique (`fingerprint`) |
| `primary_skill_id` | uuid FK skills | |
| `label` | text | generic role label, e.g. "FastAPI backend · API design, databases, authentication" (no project title) |
| `competencies` | jsonb | `[{competency_id, code, name, weight_bp, question_count, reasons: [text]}]`, weights sum to 10000 |
| `question_count` | smallint | default 12 (setting) |
| `time_limit_seconds` | integer | default 900 (setting) |
| `difficulty_mix` | jsonb | `{"easy": 4, "medium": 5, "hard": 3}` |
| `pass_rule` | jsonb | `{"overall_bp": 6000, "floor_bp": 4000, "heavy_weight_bp": 2000}` |
| `status` | enum (`AVAILABLE`, `UNAVAILABLE`) | UNAVAILABLE when the bank can't support it (§5.4) |
| `unavailable_reason` | text, nullable | |
| `created_at` | timestamptz | |

Blueprints are **immutable** once created (trigger). The same fingerprint is shared by every slot with identical requirements, so reuse works naturally. RLS: readable by all signed-in users (no secrets); inserted only through `create_slot_assessment` (§10). The stored `status` describes the bank at creation time; whether an attempt can start **now** is checked at runtime (§5.4).

### 4.4 `slot_assessments` (new)
| Column | Type | Rules |
|---|---|---|
| `slot_id` | uuid PK, FK project_slots | one per slot |
| `project_id` | uuid FK projects | |
| `blueprint_id` | uuid FK assessment_blueprints | |
| `requirements_hash` | char(64) | hash of the inputs used (§5.1), for audit |
| `created_at` | timestamptz | |

Created inside the **publish transaction** (DRAFT → BIDDING). When the "too few bids" actions change slots, links are created for new slots and kept for existing ones. RLS: readable by anyone who can see the project; writable only by the SYSTEM path.

### 4.5 `test_attempts` (extend; the same table serves practice tests and role assessments)
Add:
| Column | Type | Rules |
|---|---|---|
| `kind` | enum (`PRACTICE`, `ROLE`) | default `PRACTICE`; existing rows PRACTICE |
| `blueprint_id` | uuid FK, nullable | required when ROLE; `test_id` required when PRACTICE (CHECK: exactly one) |
| `context_project_id`, `context_slot_id` | uuid, nullable | where the role attempt was started (audit only) |
| `current_index` | smallint default 0 | ROLE only: index of the question currently shown |
| `answers_locked` | jsonb default `[]` | ROLE: `[{question_id, choice or null, answered_at}]` in order |
| `attempt_token_hash` | bytea, nullable | ROLE: SHA-256 of the per-window attempt token (§6.6) |
| `consent_at` | timestamptz, nullable | required for ROLE |
| `rules_version` | smallint, nullable | version of the rules shown on the consent screen |
| `focus_leaves` | smallint default 0 | |
| `focus_events` | jsonb default `[]` | ≤ 30 entries: `{seq, type, server_at, client_at}` |
| `last_focus_seq` | integer default 0 | idempotency for focus events |
| `last_heartbeat_at` | timestamptz, nullable | |
| `connection_gaps` | smallint default 0 | heartbeats missing > 60 s (recorded, not a leave) |
| `terminated_reason` | enum (`FOCUS_LIMIT`, `EXPIRED`, `ADMIN_VOID`), nullable | |
| `breakdown` | jsonb, nullable | `[{competency_id, code, name, weight_bp, earned_w, possible_w, score_bp}]` |
| `overall_bp` | integer, nullable | 0–10000 |
| `passed` | bool, nullable | |
| `flagged` | bool default false | set on termination, admin review queue |
| `extra_time_seconds` | integer default 0 | from accommodation (§12.3) |
| `reused_seen` | bool default false | selection had to reuse questions the user saw recently (§5.2) |
| `admin_reviewed_at`, `admin_reviewed_by` | timestamptz / uuid, nullable | set by "Mark reviewed" (§12.1) |
| `seed` | bigint | exists; reuse |

Reuse existing columns instead of adding new ones: `question_ids` (ordered list of the attempt's questions), `started_at`, `deadline_at`, `submitted_at` (= scoring time), `score`, `scored`. **Verify their exact names in migration 0004.** State is derived: **OPEN** ⇔ `submitted_at IS NULL`; **SCORED** ⇔ `submitted_at IS NOT NULL AND scored`.

Indexes: partial `(user_id) WHERE submitted_at IS NULL` (one open attempt check), `(blueprint_id, user_id, submitted_at)`, partial `(submitted_at) WHERE flagged`.

### 4.6 `skill_evidence` (extend)
- Add enum value `ROLE_ASSESSMENT` to `evidence_source` (migration must handle enum alteration safely; downgrade removes rows of that source first).
- Add `blueprint_id` (uuid FK, nullable; required when ROLE_ASSESSMENT), `passed` (bool, nullable), `valid_until` (timestamptz, nullable), `voided_at` (timestamptz, nullable), `void_reason` (text, nullable).
- A ROLE_ASSESSMENT evidence row is written for **every scored role attempt** (passed or not), so history is complete; only rows with `passed = true`, `voided_at IS NULL` and `valid_until > now()` satisfy the newcomer rule.

### 4.7 `bids` (extend)
- Add `assessment_evidence_id` (uuid FK skill_evidence, nullable). Set by the server when a newcomer's bid is created or its slot changes. Never accepted from the client.

### 4.8 `user_accommodations` (new)
`user_id` PK, `extra_time_pct` (0, 25 or 50), `note` (≤ 300 chars, admin-only), `granted_by`, `granted_at`. Owner can read their own row; admins manage.

### 4.9 Platform settings (add, validated, versioned like existing settings)
| Key | Default | Range |
|---|---|---|
| `assessment.question_count` | 12 | 8–20 |
| `assessment.time_limit_seconds` | 900 | 300–2400 |
| `assessment.difficulty_mix` | 4 / 5 / 3 | sums to question_count |
| `assessment.pass_overall_bp` | 6000 | 4000–9000 |
| `assessment.floor_bp` | 4000 | 0–7000 |
| `assessment.heavy_weight_bp` | 2000 | 1000–4000 |
| `assessment.validity_days` | 180 | 30–365 |
| `assessment.retake_days` | 30 | 1–90 |
| `assessment.leave_limit` | 2 | 1–3 |
| `assessment.leave_debounce_ms` | 3000 | 500–10000 |
| `assessment.allow_back_navigation` | false | bool (true restores free navigation for experiments only) |
| `assessment.min_approved_per_competency` | 4 | 2–20 |
| `assessment.require_human_review` | false | bool; when true, only `HUMAN_APPROVED` questions are used (turn on after the team review) |

Changing settings never affects existing blueprints or attempts (they store their own values).

---

## 5. Algorithms (pure, in `backend/app/algorithms/`; deterministic; no DB, web, clock or network)

### 5.1 Blueprint builder — `role_blueprint.py`

**Input** (`BlueprintInput`):
- `primary_skill`: `{id, name}` of the slot's skill
- `milestones`: `[{skill_ids: [...]}]` for all milestones of the project
- `text`: project title + summary + description + requirements (already stored, plain text)
- `catalogue`: competencies for all skills: `{skill_id: [{id, code, name, is_core, keywords, position}]}`
- `bank_counts`: approved question counts per `(competency_id, difficulty)`
- `params`: question_count, difficulty_mix, pass_rule, `min_approved_per_competency`

**Steps:**
1. **Normalize text:** NFC, lowercase, collapse whitespace, strip control characters; cap at 20,000 characters.
2. **Related skills:** among milestones that include the primary skill, count how often each **other** skill appears. Keep the top **2** by count (ties by skill name, then id). Ignore related skills with count 0.
3. **Candidate competencies:** all active competencies of the primary skill, plus the **core** competencies of each related skill.
4. **Base points:** primary-skill competencies share **80** points equally; related-skill competencies share **20** points equally (if there are no related skills, primary gets 100).
5. **Keyword boost:** for each candidate, count whole-word matches (`\b`-bounded, phrases allowed) of its keywords in the text; each keyword counts at most 3 times; `boost = min(total_hits, 5) × 4` points.
6. **Score** = base + boost. Sort by score (desc), then `is_core` (desc), then `position`, then `code`.
7. **Select 4–6 competencies:** take the top 6, but (a) at least 3 must belong to the primary skill (replace the lowest related ones if needed), and (b) drop any competency whose bank can't supply its share (step 9). Fewer than 4 left, or fewer than 3 from the primary skill → blueprint `UNAVAILABLE` with reason `INSUFFICIENT_COMPETENCIES` or `INSUFFICIENT_PRIMARY_COMPETENCIES`.
8. **Weights:** normalize scores to basis points summing to 10,000; clamp each to **[1,000, 4,000]**, re-normalize iteratively; **round to multiples of 500**; fix the rounding difference on the largest weight so the sum is exactly 10,000; if that pushes it above 4,000, move the excess in steps of 500 to the next-largest weights that are below 4,000 (if every weight is at 4,000 the set is invalid and the lowest competency is dropped). Ties in "largest" are broken by `code`. (Rounding to 500 makes fingerprints stable against tiny text changes.)
9. **Question allocation:** distribute `question_count` by weight with the largest-remainder method, **minimum 1** each. Then assign the global difficulty mix: walk competencies in weight order and, round-robin, give each question slot the difficulty with the highest remaining global need **that the competency's approved pool can supply** (ties: medium, then easy, then hard). If a competency can't supply its allocation at any difficulty (needs at least `min_approved_per_competency` approved questions overall and enough per assigned difficulty + 1 spare), remove it and restart from step 8. Store `question_count` and the per-difficulty allocation per competency.
10. **Reasons** (plain language, max 3 per competency): "Core skill of this role (FastAPI)"; "The requirements mention: login, user roles"; "PostgreSQL is needed in 3 milestones of this role".
11. **Label:** `"{primary skill} · {top 3 competency names}"`.
12. **Fingerprint:** SHA-256 of canonical JSON (sorted keys, no spaces) of `{algo_version, primary_skill_id, competencies: [[code, weight_bp, question_count, {easy, medium, hard}] sorted by code], time_limit_seconds, pass_rule}`.

**Output:** `Blueprint` dataclass with all fields of §4.3, or `Unavailable(reason)`.

**Determinism:** same input → identical output and fingerprint. Text not affecting matches → same fingerprint. Property-tested (§17).

### 5.2 Question selection — `assessment_selection.py`

**Input:** blueprint, candidate pool `[(question_id, competency_id, difficulty, times_served)]` (approved only, from a definer view that **excludes answers**), `recently_seen` (question ids this user saw in **any** attempt, practice or role, in the last 180 days), seed.
**Algorithm:**
1. For each competency and difficulty slot in the blueprint allocation, build the eligible pool (that competency and difficulty).
2. Prefer questions **not** in `recently_seen`; only if none remain, allow recently seen ones (record `reused_seen = true` on the attempt).
3. Among preferred questions, take the 5 with the lowest `times_served` and pick one at random (seeded "randomesque" exposure control).
4. No question twice in one attempt.
5. **Order** (deterministic given the chosen questions): keep a queue of competencies sorted by weight (desc, then code). Walk the repeating difficulty pattern **medium, easy, hard**; for each pattern step, take the next competency in the queue that still has an unplaced question of that difficulty, place it, and move that competency to the back of the queue; if no competency has that difficulty left, skip to the next pattern step. Repeat until all questions are placed. So the test starts with a medium question and alternates competencies.
**Output:** ordered list of `question_count` question ids. If impossible (pool changed since blueprint creation), raise `SelectionUnavailable` → `409 BLUEPRINT_UNAVAILABLE` and the slot falls back as in Decision 10.

### 5.3 Scoring — `assessment_scoring.py` (Python reference) **and** the same formula in SQL (§10)

- Weight per question: easy 2, medium 3, hard 4. Unanswered (skipped or expired) = wrong.
- Per competency: `score_bp_c = floor(10000 × earned_w_c / possible_w_c)`.
- Overall: `overall_bp = floor( Σ_c weight_bp_c × score_bp_c / 10000 )`.
- **Pass** ⇔ `overall_bp ≥ pass_overall_bp` **and** for every competency with `weight_bp ≥ heavy_weight_bp`: `score_bp_c ≥ floor_bp`.
- **Terminated** (`FOCUS_LIMIT`) or **voided** ⇒ `passed = false` regardless of score.
- Evidence `score` (numeric 0–1, 3 decimals) = `overall_bp / 10000` rounded **down** to 3 decimals.
- Integer arithmetic only; no floats. Python and SQL must agree on all shared vectors (§17.2).

### 5.4 Availability and fallback
A blueprint is `AVAILABLE` only if step 9 succeeded. **Runtime availability:** the status endpoint and every start re-run the selector as a dry run against the current pool (approved questions, and only `HUMAN_APPROVED` ones when `assessment.require_human_review = true`). If selection is impossible (questions retired, or the human-review switch narrowed the pool), the effective status is unavailable for now and the fallback applies, without changing the stored blueprint. If `UNAVAILABLE`, the slot's link still stores it (for transparency) and the newcomer rule for that slot uses the **practice test evidence** of the slot's skill (Decision 10). The bid sheet shows: "A role assessment isn't available for this role yet, so your practice test result for FastAPI is used."

---

## 6. Attempt lifecycle and rules

### 6.1 States
`OPEN` → `SCORED` (normal finish, submit, or expiry) · `OPEN` → `SCORED` with `terminated_reason = FOCUS_LIMIT` · `SCORED` → (admin) `voided` via evidence `voided_at` (attempt keeps its history). Invalid transitions return `409 INVALID_STATE` with `current_state` and `allowed_actions`.

### 6.2 Who may start
A developer may start a role attempt for `(project, slot)` only if **all** hold (checked server-side, in this order, each with its own error code):
1. Authenticated user with role **developer** → else `403 ROLE_NOT_ALLOWED`; account `ACTIVE` with phone and email verified → else `403 ACCOUNT_NOT_VERIFIED`.
2. Project visible to them → else `404`; project in `BIDDING` and `now < bidding_deadline` → else `409 BIDDING_CLOSED`.
3. Slot belongs to the project → else 404.
4. The developer has the slot's skill on their profile → else `409 SKILL_NOT_ON_PROFILE`.
5. They are a **newcomer** (existing `reputation_read` rule) → else `409 NOT_REQUIRED`.
6. Slot blueprint is `AVAILABLE` → else `409 BLUEPRINT_UNAVAILABLE` (fallback applies).
7. No valid passing result with the same fingerprint → else `409 ALREADY_PASSED` (with the evidence summary).
8. No other **open** attempt of any kind → else `409 ATTEMPT_OPEN` (with its id and kind; the UI offers "Resume").
9. Retake allowed: no scored attempt for this fingerprint within `retake_days` → else `409 RETAKE_LOCKED` with `next_allowed_at`.
10. `consent: true` and the current `rules_version` in the request → else `422 CONSENT_REQUIRED`.

Rules 1–6 and 10 are checked by the service; rules 7–9 are re-checked inside `start_role_attempt` under the per-user advisory lock (so two parallel starts can't both pass). The newcomer check (rule 5) uses the existing `reputation_read` service in the same transaction.

Starting is idempotent with `Idempotency-Key` (spec §10.1).

**Bidding deadline check:** if bidding closes before `now + time_limit + 5 minutes`, the status endpoint returns `bidding_closes_soon: true` with the closing time, and the consent screen shows: "Bidding for this project closes at 18:30. You may not have time to place your bid after the assessment." Starting is still allowed (the result is reusable for other slots with the same fingerprint).

### 6.3 Time
- Server deadline = `started_at + time_limit_seconds + extra_time_seconds`.
- Responses always include `server_now` and `deadline_at`; the client computes the offset and counts down from server time (never from its own clock alone).
- Answers arriving after `deadline_at + 5 s grace` are rejected and the attempt is scored as expired.
- **Immediate scoring after the deadline:** any request about an open attempt whose deadline (+ grace) has passed (get, answer, focus event, heartbeat, result) first scores the attempt inside the same transaction and then responds with the result. The client also requests the result as soon as its countdown reaches zero. So a candidate who returns to a hidden tab sees the result at once.
- The existing expiry job also scores open ROLE attempts whose deadline has passed (`terminated_reason = EXPIRED` is **not** set for normal expiry; `EXPIRED` is reserved for attempts abandoned with no answers, for reporting only).

### 6.4 One-way navigation
- The server serves **only the current question** (`current_index`); previous questions are never re-sent.
- An answer is accepted only for the current question id; it locks the answer and advances `current_index`.
- **Skip** is allowed (choice `null`), counts as wrong, and locks the question. The UI asks for confirmation ("Skip this question? You can't come back to it.").
- After the last question the attempt is scored immediately.
- **Finish early:** the candidate may end the attempt; remaining questions count as wrong; confirmation required.

### 6.5 Results
After scoring, the candidate sees: overall score (0–100), pass/fail, per-competency scores with weights, strongest and weakest competency, `valid_until` if passed, `next_allowed_at` if failed or terminated. **Correct answers and per-question correctness are never shown** (protects the bank).

### 6.6 Single window (attempt token)
- On start or resume, the server issues a random 256-bit **attempt token** (returned once, stored hashed) for that window; every answer, focus event and heartbeat must send it in the `X-Attempt-Token` header.
- **Resume** (crash, reload, another device) issues a new token and invalidates the old one; the old window's next request gets `409 ATTEMPT_MOVED` and shows "This assessment continued in another window."
- Resume is allowed while the attempt is open; the deadline does not change.

### 6.7 Retakes and validity
- Retake: one **scored** attempt per fingerprint per `retake_days` (terminated attempts count; **voided** attempts don't, so an admin void allows an immediate retake).
- Validity: a passed result satisfies the newcomer rule for **any slot with the same fingerprint** until `valid_until = submitted_at + validity_days (the scoring time)`.
- A bid placed while the result was valid stays linked to it (`bids.assessment_evidence_id`) even if it later expires; new bids need a valid result.

---

## 7. Focus mode and the two-leave rule

### 7.1 Consent screen (required before starting)
Shown in the assessment panel, with a checkbox "I understand and agree" and the rules version. Text (keep it short and plain):
> - This assessment has **12 questions** and **15 minutes** in total.
> - Questions appear **one at a time**. Once you answer or skip a question, you **can't go back**.
> - The assessment opens in **full screen**. Leaving full screen (including pressing **Esc**), switching tabs, windows or apps, or closing/reloading the page counts as **leaving**.
> - The **first** time you leave, you'll get a warning and can continue (the timer keeps running).
> - The **second** time, the assessment **ends**. It's scored but **can't count as a pass**, and you can retake it after 30 days.
> - We only record when you leave this page. We never record your screen, camera or keystrokes.
> - Your result shows your competency for this role. It doesn't count as completed work.

### 7.2 Entering focus mode
- On "Start" (a user gesture), call `document.documentElement.requestFullscreen({ navigationUI: "hide" })`.
- If unsupported or refused (e.g. iPhone Safari, which doesn't support full screen for pages): continue in **focus layout** (full-height panel, app chrome hidden, scroll locked) and record `fullscreen_supported: false` in the first focus event batch; tab/window detection still applies.

### 7.3 What counts as one "leave" (client detection, `useFocusGuard` hook)
- `document.visibilityState` becomes `hidden` (tab switch, minimize, app switch on mobile, reload, close).
- Leaving full screen (`fullscreenchange` with `document.fullscreenElement === null`) **when full screen was active**.
- Window `blur` **not followed by `focus` within `leave_debounce_ms`** (3 s): short blurs from OS notifications are ignored.
- **Coalescing:** events within 5 seconds of each other count as **one** leave (e.g. exiting full screen and switching tab together). Only counted leaves get a new `seq`.
- Detection starts after the first question is shown and stops when the attempt is scored.

### 7.4 Reporting and server rules
- The client sends `POST /assessment-attempts/{id}/focus-events` with `{seq, type, client_at}` (`seq` increments per leave; retried until acknowledged; queued if offline and sent on reconnect).
- The server is **idempotent by `seq`** (ignores `seq ≤ last_focus_seq`), appends to `focus_events` (max 30; further events only increment a counter), increments `focus_leaves`, and returns `{focus_leaves, status}`:
  - `focus_leaves < leave_limit` → `WARNING`
  - `focus_leaves ≥ leave_limit` → the server **immediately scores** the attempt with `terminated_reason = FOCUS_LIMIT`, `passed = false`, `flagged = true`, and returns `TERMINATED` with the result.
- **Sending during unload:** when the page becomes hidden, the leave is sent with `fetch(..., { keepalive: true })` (which, unlike `sendBeacon`, can carry the `X-Attempt-Token` and CSRF headers) and is also written to `sessionStorage` (`devsync:pending-leaves:{attemptId}`, only `{seq, type, client_at}`). On reload or resume in the same tab, pending leaves are re-sent and removed once acknowledged; the server's seq idempotency prevents double counting. A crash on another device can lose a leave; this is an accepted limit (§7.7). Resume itself is not an extra leave.
- **Heartbeat:** while open, the client sends `POST /heartbeat` every 15 s with `{visible: bool, fullscreen: bool}`. Gaps are measured by the server when the next request arrives (or when the attempt is scored): if more than 60 s passed since `last_heartbeat_at` while the attempt was open, it records a `connection_gap` (not a leave); a gap over 2 minutes sets `flagged = true` (admin sees "long disconnection"). Gaps never terminate an attempt.

### 7.5 After a warning
A blocking overlay: "You left the assessment. This is your only warning; leaving again will end it." with a "Return to full screen" button (user gesture re-requests full screen). If the browser refuses or doesn't support full screen, the overlay offers "Continue without full screen" and the attempt continues in focus layout (tab and window detection still apply; full-screen exits can no longer occur, so they are not counted). The overall timer keeps running on the server.

### 7.6 Other friction (speed bumps, not security)
Disable text selection and the copy event on question text and options (but never block screen readers, zoom, or keyboard navigation); disable the context menu inside the question area; no print styles for the assessment panel.

### 7.7 Honest limits (put in docs and the viva notes)

For Demo 1 the question bank is **self-verified** (code answers proven by running the code, every question independently re-solved); the team's human review follows after Demo 1. Say this openly if asked.

Detection runs in the browser and can be bypassed by a technical user; a second device can't be detected. The **server-side** guarantees are the deadline, one-way navigation, hidden answers and single-window tokens. The assessment only opens the door; real project evidence decides the rest.

---

## 8. Integration with bidding and Algorithm 1

### 8.1 Status endpoint drives the bid sheet
`GET /projects/{project_id}/slots/{slot_id}/assessment` returns one of:
| `status` | Meaning | UI |
|---|---|---|
| `NOT_REQUIRED` | Not a newcomer, or `pcs_replication` mode | Hide the section |
| `REQUIRED` | Newcomer, no valid result | "Role assessment required" card with competencies, duration, Start |
| `IN_PROGRESS` | Open attempt for this blueprint | Resume |
| `OPEN_ELSEWHERE` | Open attempt for a different test/blueprint | "Finish or let your other assessment expire first" + link |
| `PASSED` | Valid passing result (same fingerprint) | Green badge with score, valid until; bid can be placed |
| `RETAKE_LOCKED` | Failed or terminated, cooling down | Result summary + "You can retake on {date}" |
| `FALLBACK_PRACTICE` | Blueprint unavailable now | Explanation + practice test result or link |
| `CLOSED` | Bidding closed or project not in BIDDING | "Bidding has closed for this project" |
| `BLOCKED` | Account not verified, or skill missing from profile (`reason`: `ACCOUNT_NOT_VERIFIED` / `SKILL_NOT_ON_PROFILE`) | Guidance with a link ("Verify your phone", "Add React to your profile") |
Clients and admins calling this endpoint get `403 ROLE_NOT_ALLOWED`. The frontend refetches the status after any attempt state change (TanStack Query invalidation) and whenever the bid sheet regains focus.
Also returns the blueprint summary (label, competencies with weights and reasons, question count, time limit), `rules_version`, and the developer's latest result for this fingerprint.

### 8.2 Filtering change (minimal)
- In `filtering.py`, extend `NewcomerEvidence` with `assessment_passed: bool | None` (None = not a role assessment) and keep everything else. The newcomer evidence check becomes: `score ≥ newcomer_pass_mark` **and** `assessment_passed is not False`.
- In `services/bids.py`, for newcomers in `devsync` mode, build the evidence from the **valid passing ROLE_ASSESSMENT evidence for the slot's blueprint fingerprint**; if the slot is in fallback, use the best TEST evidence for the skill (as today). Experienced developers: unchanged.
- Reason code stays `NO_SKILL_EVIDENCE` (stable code), with new human texts:
  - no result: "Newcomers need a passing role assessment for this role."
  - failed: "Role assessment 54 — below the pass mark of 60."
  - floor: "Role assessment 63, but authentication scored 30 (needs at least 40)."
  - terminated: "The role assessment ended early, so it can't count as a pass."
- `pcs_replication` mode: unchanged (no newcomer rule).
- Relaxation (lowering P0/C0) does **not** relax the assessment pass rule.

### 8.3 Bid creation and edits
- `POST /projects/{project_id}/bids` for a newcomer in `devsync` mode without a valid passing result for the slot → `409 ROLE_ASSESSMENT_REQUIRED` with the status payload of §8.1. With a valid result → bid created, `assessment_evidence_id` set.
- Changing a bid's slot re-checks the requirement for the new slot.
- The eligibility preview endpoint returns the assessment status for the chosen slot.
- **Eligibility of existing bids** uses the evidence linked to the bid (`assessment_evidence_id`) even after it expires, unless it was voided.
- Evidence voided by an admin → the eligibility of affected open bids is recomputed and they become ineligible with the text "Role assessment voided by an admin"; the bidder gets an in-app notification through the existing notifications service (`app/services/notifications.py`).
- **Bids created before this feature** (seed or test data) have no linked evidence; they are re-evaluated with the new rule. The stage-1 seed is regenerated so all newcomer bids are consistent.

### 8.4 Reputation
- `newcomer_snapshot`'s `evidence_domains` counts a domain if it has a **valid passing** ROLE_ASSESSMENT **or** TEST evidence ≥ pass mark (practice tests still help the starting Expertise value, as today). No new formula, no bonus.
- Newcomer status and exit are unchanged.

### 8.5 Client view
- `ClientBidsPage` and `BidExplanation` ("How the filter decided") show, for newcomer bids: "Role assessment: 78 · passed · strongest: API design · weakest: testing · taken 28 Oct". Never answers, focus events or flags (flags are admin-only).

---

## 9. API contract (all under `/api/v1`; contract-first, typed errors with examples, OpenAPI committed)

| Method & path | Who | Purpose | Rate limit |
|---|---|---|---|
| `GET /projects/{project_id}/slots/{slot_id}/assessment` | Developer | Status + blueprint summary (§8.1) | 120/min |
| `POST /projects/{project_id}/slots/{slot_id}/assessment/attempts` | Developer | Start (`{consent: true, rules_version}`, `Idempotency-Key`) → `201` attempt + token, or existing open attempt for this blueprint | 10/hour |
| `POST /assessment-attempts/{attempt_id}/resume` | Owner | New attempt token, current question | 20/hour |
| `GET /assessment-attempts/{attempt_id}` | Owner | State, `current_index`, `total`, `deadline_at`, `server_now`, `focus_leaves`; the **current question only when a valid `X-Attempt-Token` is sent** (otherwise the client must call `resume`, which rotates the token) | 120/min |
| `POST /assessment-attempts/{attempt_id}/answer` | Owner (+ token) | `{question_id, choice: 0–3 or null}` → next question or result | 120/min |
| `POST /assessment-attempts/{attempt_id}/finish` | Owner (+ token) | End early, confirm → result | 10/hour |
| `POST /assessment-attempts/{attempt_id}/focus-events` | Owner (+ token) | `{seq, type, client_at}` → `{focus_leaves, status, result?}` | 60/min |
| `POST /assessment-attempts/{attempt_id}/heartbeat` | Owner (+ token) | `{visible, fullscreen}` → `{server_now, deadline_at}` | 10/min |
| `GET /assessment-attempts/{attempt_id}/result` | Owner | Result (§6.5) | 120/min |
| `GET /me/role-assessments` | Developer | History (label, score, passed, dates, flagged? no) | 60/min |
| `GET /admin/assessments?flagged=&from=&to=` | Admin | Queue | 300/min |
| `GET /admin/assessments/{attempt_id}` | Admin | Full detail incl. focus events, gaps, per-question correctness | 300/min |
| `POST /admin/assessments/{attempt_id}/void` | Admin + step-up | `{reason ≥ 20 chars}` → voids evidence, re-evaluates bids, allows immediate retake | 30/hour |
| `POST /admin/users/{user_id}/accommodation` | Admin + step-up | `{extra_time_pct: 0/25/50, note}` | 30/hour |
| `GET/PATCH /admin/question-bank`, `POST /admin/question-bank/{id}/approve`, `/retire` | Admin | Review workflow (§12.2) | 300/min |

**Error codes** (add to the `ErrorResponse` enum): `NOT_REQUIRED`, `ALREADY_PASSED`, `ATTEMPT_OPEN`, `RETAKE_LOCKED`, `CONSENT_REQUIRED`, `BLUEPRINT_UNAVAILABLE`, `SKILL_NOT_ON_PROFILE`, `ACCOUNT_NOT_VERIFIED`, `BIDDING_CLOSED`, `NOT_CURRENT_QUESTION`, `ATTEMPT_CLOSED`, `ATTEMPT_MOVED`, `ATTEMPT_TOKEN_REQUIRED`, `ATTEMPT_TOKEN_INVALID`, `DEADLINE_PASSED`, `ROLE_ASSESSMENT_REQUIRED`, `ROLE_NOT_ALLOWED`. Every operation declares 401/403/404/409/422/429 as applicable, with examples; `check_openapi.py` must pass.

**Never accepted from the client:** user id, blueprint id (derived from the slot), score, pass status, deadline, `current_index`, focus counts, evidence id.

---

## 10. Database functions and security

Follow the migration-0004 pattern (`SECURITY DEFINER`, `SET search_path = pg_catalog, public`, `REVOKE ALL ... FROM PUBLIC`, `GRANT EXECUTE` to `devsync_app` only, caller checked with `app_uid()`, advisory lock per user on start).

| Function | Responsibility |
|---|---|
| `create_slot_assessment(p_project, p_slot, p_blueprint jsonb, p_requirements_hash)` | Called in the publish transaction (and by the "too few bids" slot actions); caller must be the project's client and the project must be moving to or in BIDDING; inserts the blueprint if its fingerprint is new (otherwise reuses it) and the slot link |
| `role_bank_counts(p_skill_ids uuid[], p_min_review_level)` | Approved question counts per `(competency, difficulty)` for the blueprint builder; no content |
| `role_question_pool(p_blueprint uuid, p_min_review_level)` | Returns `(question_id, competency_id, difficulty, times_served)` for approved questions of the blueprint's competencies at or above the review level; **no text, options or answers**; used by the Python selector |
| `user_recent_questions(p_since timestamptz)` | Question ids the caller saw in any attempt since the date |
| `start_role_attempt(p_blueprint, p_question_ids uuid[], p_now, p_seed, p_project, p_slot, p_token_hash, p_time_limit, p_extra_time, p_rules_version)` | Re-checks rules 5–9 of §6.2 inside the lock; validates the question ids (approved, belong to the blueprint, correct allocation per competency and difficulty, no duplicates); creates the attempt; increments `times_served`; returns the id |
| `role_current_question(p_attempt, p_token_hash)` | Owner + token check; returns `{index, total, question_id, text, code_snippet, options, competency_name}` for `current_index` only |
| `record_role_answer(p_attempt, p_question, p_choice, p_now, p_token_hash)` | Row lock; owner, token, `OPEN`, deadline + grace, `p_question = current question`; appends to `answers_locked`; advances; scores when last |
| `record_focus_event(p_attempt, p_seq, p_type, p_now, p_client_at, p_token_hash)` | Row lock; idempotent by seq; appends (bounded); increments; terminates and scores at the limit |
| `rotate_attempt_token(p_attempt, p_new_hash)` | Owner, `OPEN`; replaces the token hash |
| `score_role_attempt(p_attempt, p_now, p_reason)` | Row lock; idempotent (returns the stored result if already scored); integer scoring (§5.3); writes `breakdown`, `overall_bp`, `passed`, `flagged`; writes **one** ROLE_ASSESSMENT evidence row for every scored attempt (`passed`, `score`, `blueprint_id`, and `valid_until` only when passed); measures any final connection gap; audit entry |
| `void_role_attempt(p_attempt, p_reason, p_admin)` | Admin only (checked); sets evidence `voided_at`; audit |

**RLS** (spec §14.15): new tables get `ENABLE` + `FORCE ROW LEVEL SECURITY`; `check_rls.py` must pass. Attempts: owner and admins only; clients never read attempts directly (they get summaries through the bids service). `question_bank` stays unreadable to the app role except through definer functions.

**Audit actions:** `role_assessment.start`, `.resume`, `.answer` (no choice logged), `.focus_leave`, `.terminate`, `.score`, `.void`, `.accommodation`, `question.approve`, `question.retire`, `blueprint.create`.

**Logging:** never log answers, choices, tokens or question text.

---

## 11. Frontend

Use the design system, shared components, `devsync-ui` + `frontend-design` skills, light/dark, reduced motion, responsive rules (spec §13.14) and the CSP rules (no runtime `<style>` injection).

### 11.1 Files (suggested)
`frontend/src/features/assessment/`: `api.ts` (TanStack Query hooks), `AssessmentStatusCard.tsx` (in the bid sheet), `ConsentDialog.tsx`, `AssessmentRunner.tsx` (full-screen panel), `QuestionView.tsx`, `CodeBlock.tsx` (plain text, monospace, no syntax HTML injection), `CountdownTimer.tsx`, `LeaveWarningOverlay.tsx`, `ResultView.tsx`, `useFocusGuard.ts`, `useServerClock.ts`, `useBidDraft.ts`, plus tests. Admin pages under `features/admin/assessments/` and `features/admin/question-bank/`.

### 11.2 Bid sheet (`ProjectBidPage.tsx`)
- After the developer picks a slot, `AssessmentStatusCard` loads the status (§8.1) and renders the matching state. For `REQUIRED`: title "Role assessment required", one-line why ("As a new developer on DevSync, you show your competency for this role with a short assessment."), competency chips with weights and a "Why these?" disclosure listing the reasons, "12 questions · 15 minutes", primary button "Start assessment".
- The submit button is enabled for `NOT_REQUIRED`, `PASSED`, and `FALLBACK_PRACTICE` with passing practice evidence; otherwise disabled with an explanation (the server enforces it anyway).
- **Draft preservation:** `useBidDraft` keeps the form in memory and in `sessionStorage` (key `devsync:bid-draft:{project_id}`, non-sensitive fields only: slot, price, days, hours, proposal), restored on return, cleared on successful submit or logout.

### 11.3 Assessment runner
- Opens as a full-screen panel over the bid sheet (no route change, so the draft stays in memory); also deep-linkable at `/dev/assessments/{attemptId}` for resume.
- Header: role label, "Question 4 of 12", progress bar, countdown (`mm:ss`, turns amber under 2 minutes and rose under 30 seconds; `aria-live` announcements at 5, 2 and 1 minute).
- Body: question text, optional code block, 4 options as large radio cards (keyboard: 1–4 select, Enter confirms), buttons "Confirm answer" (primary) and "Skip" (secondary, with confirmation). No back button.
- Footer: "Leaving full screen or this tab counts as leaving (1 warning left)".
- Network errors: retry with backoff; answers are idempotent server-side; show "Reconnecting…" without losing the selection.
- When the timer reaches zero: show "Time's up — scoring…" and fetch the result.
- `ATTEMPT_MOVED`: show the "continued in another window" screen.

### 11.4 Result view
Score ring (0–100), "Passed" / "Not passed" / "Ended early", competency bars with weights, strongest and weakest, valid-until or retake date, short guidance ("Use the practice test for testing to improve"), and "Back to your bid". Never show correct answers.

### 11.5 Practice tests
Rename the Skill Challenges entry to **"Practice tests"**; add a note: "Practice tests help you prepare and appear on your profile as practice results. Bidding as a newcomer needs the role assessment shown on each project." Their behaviour is unchanged.

### 11.6 Profile
Section "Verified role assessments": role label, score, date, valid until; marked "Assessment result — not completed work". Practice results labelled "Practice". Visibility follows the existing profile visibility rules. Never shows project names, answers or flags.

### 11.7 Mobile and accessibility
- Phones: the runner fills the screen; options stack; buttons in a sticky bottom bar above the keyboard/safe area.
- iPhone: focus layout without full screen (§7.2), consent text says so.
- Screen readers: proper labels, `role="radiogroup"`, focus moved to the question heading on each new question; the copy-blocking never interferes with assistive technology.
- Reduced motion: no animated transitions between questions.

---

## 12. Admin tools

### 12.1 Flagged assessments
List with filters (flagged, date, skill); detail shows candidate, role label, timeline of focus events and gaps, per-question correctness and response times, result; actions: **Void** (step-up, reason) or **Mark reviewed**.

### 12.2 Question bank review
Table with filters (skill, competency, difficulty, status, source); detail with text, snippet, options, correct answer, explanation; actions: edit (DRAFT only), **Approve** (sets `status APPROVED`, `review_level HUMAN_APPROVED`, `reviewed_by_user`, `reviewed_by_name` = the admin's name, `reviewed_at`), **Retire** (blocked if it would break a practice test, §4.2); shows `times_served`, `review_level` and verification results. An approved question's content can't be edited (create a new version).

### 12.3 Accommodations
Grant extra time 25% or 50% to a user (step-up, note); applies to attempts started afterwards.

---

## 13. Question bank content

### 13.1 Competency catalogue (seed)
| Skill | Competencies (★ = core) |
|---|---|
| **React** | ★ components and props · ★ state and hooks · ★ effects and data fetching · forms and validation · performance · accessibility · testing UI |
| **FastAPI** | ★ API design and HTTP · ★ validation and schemas · ★ authentication and authorization · databases and ORM · async and performance · error handling and debugging · API security |
| **PostgreSQL** | ★ data modelling · ★ SQL queries and joins · ★ constraints and integrity · indexes and performance · transactions and concurrency · roles and row-level security |
| **Testing** | ★ test design and boundaries · ★ unit testing · ★ API and integration testing · end-to-end and UI testing · debugging and failure analysis · test automation and CI |
| **Node.js** | ★ async and event loop · ★ API building (Express) · ★ error handling · security basics |
| **UI/UX** | ★ usability principles · ★ layout and visual hierarchy · ★ accessibility · user research basics |
| **Flutter** | ★ widgets and layout · ★ state management · ★ navigation · data and APIs |
| **DevOps** | ★ containers (Docker) · ★ CI/CD · ★ deployment and configuration · monitoring and logs |

Give each competency 5–15 keywords (e.g. authentication: `login, sign in, sign-up, password, jwt, session, oauth, roles, permissions, otp, 2fa`).

### 13.2 Bank size and quality
- **Demo skills (React, FastAPI, PostgreSQL, Testing):** at least **6 approved questions per competency** (2 easy, 2 medium, 2 hard) → about 40 per skill. Other skills: at least **4 per core competency**.
- Tag all 128 existing questions with a competency and keep their difficulty; then add new questions.
- Question styles (all 4-option single answer): scenario ("A list re-renders on every keystroke. Most likely cause?"), code reading ("What does this function return?"), bug spotting ("Which line causes the bug?" with numbered lines in the snippet), best practice and security.
- Rules: one unambiguous correct answer; plausible distractors; no trick wording; no "all of the above"; snippets ≤ 25 lines; explanation written for every question.
- `build_question_bank.py` gains competency tags, status, snippets and explanations, and validates all of the above (fails the build on violations: duplicate texts, answer index out of range, missing competency, too few per competency for demo skills).

### 13.3 Claude Code builds the question bank itself

**You (Claude Code) write the entire bank**: the competency catalogue and keywords (§13.1), the competency tags and explanations for the 128 existing questions, and all new questions needed to reach the §13.2 targets, and you also **verify** them for Demo 1 (below). The team reviews them after Demo 1.

**Where the content lives:** `backend/scripts/seed_data/question_bank/{skill}.yaml` (one file per skill), loaded by `build_question_bank.py`. Each question: `id` (stable slug), `competency`, `difficulty` (1–3), `text`, optional `code_snippet`, `options` (4), `correct_index`, `explanation`, `status`, `source`, `active`, `review_level`, `reviewed_by_name`, `reviewed_at`, `verification`. New questions start as `status: DRAFT`, `source: CLAUDE_GENERATED`, `active: false`, `review_level: NONE`. The 128 existing questions keep `source: HUMAN`, `active: true`, and go through the **same** self-verification before becoming `APPROVED / SELF_VERIFIED` for role use (practice tests keep using them either way).

**Self-verification before handing anything to the team (mandatory):**
1. **Execute every code question.** For each question with a `code_snippet` whose answer depends on what the code does (output prediction, bug spotting), write a small check under `backend/scripts/question_checks/` that actually runs the snippet in the terminal (Python with the project's Python; JavaScript/TypeScript with Node; SQL against the local test PostgreSQL) and asserts that the correct option is right and every distractor is wrong. `make question-checks` runs them all; the bank build fails if any check fails. Questions that can't be checked by execution are marked `check: manual`.
2. **Solve independently.** For every question, re-solve it from the text alone without looking at `correct_index`; if your answer differs, or more than one option could be defended, rewrite the question.
3. **Quality rules** (§13.2): one unambiguous answer, plausible distractors, no "all/none of the above", no trick wording, snippets ≤ 25 lines, difficulty matches the label (easy = recall or simple application; medium = applying to a scenario; hard = combining ideas or spotting subtle bugs), no near-duplicates (a script compares normalized texts and flags pairs with high similarity).
4. **Balance:** correct answers spread evenly across positions A–D within each skill (the builder checks it); every competency has the required count per difficulty.

**Additional checks because there is no human review before Demo 1 (mandatory):**
5. **Independent second solve by a fresh reviewer.** For every question, launch a separate subagent (or a fresh context) that sees **only** the question text, snippet and options, never the marked answer or explanation, and asks it to answer and to say whether any other option is defensible. A question is usable only if (a) the reviewer picks the marked answer, (b) it reports no other defensible option, and (c) for code questions the execution check passed. Record the result in `verification`.
6. **Rewrite or drop** any question that fails a check; never "fix" a failure by changing the marked answer without re-running all checks. Questions that still fail stay `DRAFT`.
7. **Difficulty sanity:** the independent reviewer also rates difficulty; if it differs by 2 levels from the label, relabel and re-check allocation counts.
8. **Report:** write `docs/question-review/verification-report.md` with, per skill: number of questions, how many verified by execution, by independent solve only, how many dropped or rewritten, and the remaining risks.

**Marking questions usable for Demo 1:**
- Questions passing all checks get `status: APPROVED`, `review_level: SELF_VERIFIED`, `reviewed_by_name: null`, `reviewed_at` = verification time, plus the `verification` record. These are used by role assessments while `assessment.require_human_review = false`.
- **Never** set `review_level: HUMAN_APPROVED`, `reviewed_by_name` or `reviewed_by_user` yourself; those are only for the team's review.
- The admin question-bank screen and the YAML clearly show "Self-verified — awaiting team review".

**Team review after Demo 1 (prepare it now):**
- Generate `docs/question-review/{skill}.md`: each question with competency, difficulty, snippet, options, marked answer, explanation and verification results, and a line `Approved by: ______` per question.
- `make question-approve FILE=docs/question-review/{skill}.md` reads the filled-in file and sets `review_level: HUMAN_APPROVED`, `reviewed_by_name`, `reviewed_at` for approved questions; questions with correction notes are **retired and replaced** by a corrected new version (`DRAFT`, then verified again). Results already earned with a retired question stay valid; the tool lists the attempts that used it so the team can decide.
- When every question in use is human-approved, the team switches `assessment.require_human_review` to `true` (recorded in `DECISIONS.md`).

**Priority if time is short:** complete and verify the four demo skills (React, FastAPI, PostgreSQL, Testing) first; the other four skills can follow after Demo 1 (their slots use the practice-test fallback until then, Decision 10).

---

## 14. Seed data and the Demo 1 walkthrough

### 14.1 Stage 1 seed (`make seed-demo STAGE=1`)
- Competencies, the tagged and expanded bank (approved), blueprints created when the seeded projects are published.
- **Nadia Rahman** (newcomer): a scored, **passed** role assessment for the React slot of "Online ordering system" (e.g. 82, all competencies ≥ 40) — replaces her old generic test as bidding evidence; her practice React test stays as a practice result.
- **Mehjabin Chowdhury** (newcomer): passed for the Testing slot.
- **Lamia Akter** (newcomer): **failed** FastAPI role assessment (e.g. 52) → still rejected as `NO_SKILL_EVIDENCE`, with the new text. The build spec §18.4 expected counts (10 eligible, Shakib TOO_SLOW, Lamia NO_SKILL_EVIDENCE) must stay true; update tests and the seed assertions accordingly.
- **New demo newcomer "Rafsan Haque"** with a verified account and the React skill but **no** role assessment, for taking it **live** in the demo.
- One flagged, terminated attempt (for the admin queue) on a seeded test account.
- **Demo answer key (operator tool, no HTTP access):** the demo stack runs with `DEVSYNC_ENV=production`, so the answer key must not be an app feature. Instead, `make demo-answer-key USER=rafsan` runs a **command-line script on the demo laptop** that connects to the demo database with the **migrator credentials** (operator-only, never available to the web app), waits for that user's next role attempt to start (`--watch`, polling every 2 s, timeout 30 min), then prints each question's number, competency and the correct option letter, and writes `runs/demos/answer-key.json` (gitignored). The presenter runs it on a second screen **before** pressing Start and simply reads it (no clicking, so no leave is triggered). The script refuses to run unless `DEVSYNC_DEMO_TOOLS=1` is set in the shell and the database name ends with `_demo`; it never runs inside the app containers. The Playwright demo test uses the same script (spawned as a child process) to answer correctly.
- **Rafsan's bid values** for the walkthrough: React slot, ৳16,000, 20 days, 20 hours/week, a short proposal; chosen so every other Algorithm 1 check passes.

### 14.2 Demo 1 walkthrough (`frontend/e2e/demos/demo-1.spec.ts`) — update
Wherever the existing walkthrough says a newcomer "passes a timed skill test", change it to a **practice test** (still allowed, shown as practice). After the existing steps up to placing sealed bids, add:
1. Sign in as **Rafsan** → open "Online ordering system" → choose the React slot → the card shows "Role assessment required" with competencies and reasons.
2. Start (the answer-key script is already watching) → consent screen → full screen (Chromium) → answer all 12 questions using the printed key → result screen shows score and competency breakdown.
3. Back in the bid sheet the draft is intact; place the bid → eligible.
4. Sign in as the client → Bids table → Rafsan's row shows the assessment line in "How the filter decided"; Lamia's row shows the failed-assessment text.
5. (Optional) Admin → flagged assessments → open the seeded terminated attempt.
Keep the whole walkthrough runnable on Chromium, Firefox, WebKit and iPhone 14 (WebKit/iPhone use the focus layout path).

---

## 15. Security checklist for this feature (each item has a test)

- Answers never leave the database (schemas and responses audited by a test that inspects every assessment response for `correct`/answer fields).
- Every route: authentication, role, ownership (404 for others' attempts), rate limit, CSRF (unsafe methods), idempotency where stated.
- Server decides newcomer status, blueprint, eligibility, deadline, current question, pass/fail; client values ignored.
- One-way navigation enforced in SQL (`NOT_CURRENT_QUESTION`).
- Single-window tokens: required, hashed at rest, rotated on resume, constant-time comparison.
- Advisory lock and re-checks prevent parallel starts; row locks prevent double answers and double scoring; scoring idempotent.
- Focus events: idempotent by seq, bounded storage, can't reduce `focus_leaves`, can't be sent for a scored attempt.
- RLS on all new tables; `check_rls.py` passes.
- Input bounds: `choice ∈ {0,1,2,3,null}`, `seq` 1–100, `type` enum, `client_at` within ±1 day of server time (otherwise stored as null), body ≤ 2 KB.
- Bid creation can't reference another developer's evidence (server sets `assessment_evidence_id`).
- Admin void and accommodation require step-up and are audited.
- No answers, choices, tokens or question text in logs.
- Demo answer key is a command-line operator tool only: no HTTP route, never imported by the app, requires `DEVSYNC_DEMO_TOOLS=1` and a `_demo` database (test proves the app has no such route and the script refuses otherwise).
- `Permissions-Policy` must **not** block full screen: keep `fullscreen` unrestricted for the site's own origin (don't add `fullscreen=()`); a test checks the header.
- Privacy: focus events and heartbeats are personal data; they are deleted with the attempt history when an account is deleted (spec §14.4 deletion), and kept only as long as attempts are kept.
- `/security-review` run on the diff; findings fixed or justified in `docs/security-reviews/role-assessment.md`.

---

## 16. Corner cases (all must be handled and tested)

**Starting**
1. Two clicks on Start / two tabs starting at once → one attempt (lock + idempotency key).
2. Start while a practice test is open → `409 ATTEMPT_OPEN` with resume link.
3. Bidding deadline passes between status check and start → `409 BIDDING_CLOSED`.
4. Developer becomes experienced (completes 3rd project) → status `NOT_REQUIRED`; an open attempt can still be finished but isn't needed.
5. Developer removes the skill from their profile mid-attempt → attempt continues; bid creation requires the skill again.
6. Account suspended mid-attempt → next request 403; attempt expires and is scored by the job.
7. Slot removed by the client ("reduce team") while an attempt is open → attempt continues; result reusable for any slot with the same fingerprint.
8. Blueprint becomes unavailable because questions were retired after creation → selection fails → `BLUEPRINT_UNAVAILABLE`, fallback shown; existing results stay valid.
9. Same fingerprint on two different projects → passing once satisfies both.
10. Small text edit in a draft project before publishing → may or may not change the fingerprint (weights rounded to 500 bp); after publishing, blueprints are frozen.

**During**
11. Answer for a question other than the current one (old tab, replay) → `NOT_CURRENT_QUESTION`.
12. Same answer sent twice (retry) → second ignored, same next question returned.
13. Answer exactly at deadline + 4 s → accepted (grace); + 6 s → rejected, attempt scored.
14. Client clock wrong by hours → countdown uses server offset.
15. Network drops for 30 s → reconnecting state; heartbeats resume; no leave counted unless the page was hidden.
16. Laptop sleeps → visibility hidden → counts as a leave (disclosed in consent).
17. OS notification steals focus for < 3 s → ignored.
18. Exit full screen and tab switch together → one leave (coalescing).
19. Leave event sent twice → counted once (seq).
20. Leave event arrives after the attempt was scored → ignored.
21. Second leave while an answer request is in flight → whichever commits first wins; the other gets `ATTEMPT_CLOSED` and shows the result.
22. Reload → counts as one leave; resume issues a new token; the deadline is unchanged.
23. Resume on another device → old window gets `ATTEMPT_MOVED`.
24. Full screen refused by the browser → focus layout; detection still works.
25. iPhone → no full screen; visibility detection only.
26. Screen-reader user → copy blocking doesn't interfere; accommodation extra time if granted.
27. Skip all questions → score 0, not passed, retake after 30 days.
27a. Candidate presses Esc → full screen exits → counted as a leave (disclosed in consent).
27b. After a warning, the browser refuses to re-enter full screen → "Continue without full screen" works; only tab/window leaves count afterwards.
27c. Time runs out while the tab is hidden → on return, the first request scores the attempt and shows the result immediately (no waiting for the job).
27d. Bidding closes in less than the assessment duration → warning on the consent screen; attempt allowed; bid creation afterwards gets `BIDDING_CLOSED`.
27e. Leaving before the first question appears (on the consent screen) → not counted.

**Scoring and results**
28. Exactly 60% overall and every heavy competency exactly 40% → **pass** (inclusive).
29. 59.99% (bp 5999) → fail.
30. Heavy competency (weight exactly 20%) at 39.99% → fail even with a high overall score.
31. Competency with weight 15% at 0% → may still pass overall (not heavy).
32. Terminated with a high score → not passed, flagged.
33. Scoring called twice (job + last answer) → idempotent, one evidence row.
34. Result requested before scoring → `409 INVALID_STATE` with `allowed_actions: ["answer", "finish"]`.

**Bidding**
35. Newcomer bids without a result → `409 ROLE_ASSESSMENT_REQUIRED`.
36. Newcomer bids with a passed result for a different fingerprint → rejected.
37. Result expires after the bid was placed → the bid stays linked and eligible; new bids need a new result.
38. Admin voids the result → open bids re-evaluated → ineligible with reason; notification.
39. Experienced developer → unchanged flow; status `NOT_REQUIRED`.
40. `pcs_replication` mode → newcomer rule off; status `NOT_REQUIRED`; tests confirm unchanged Phase 5 behaviour.
41. Threshold relaxation doesn't change the assessment pass rule.
42. Client view never exposes flags, focus events or answers.

**Bank, review and admin**
43. An admin voids an attempt → evidence voided; the developer can retake immediately (voided attempts don't count toward the retake limit).
44. `assessment.require_human_review` switched on while some questions are only self-verified → blueprints that can't be served become unavailable at runtime → fallback; nothing stored is changed.
45. Retiring a question that would leave a practice test with too few active questions → refused with a clear message.
46. A practice test never shows a new role-assessment question (`active = false`).
47. A question seen in a practice attempt within 180 days is avoided in role selection where possible.
48. Team approval file names a reviewer for a question that failed self-verification → the tool refuses (only verified questions can be human-approved).
49. Correcting an approved question → old row retired, new version created; attempts that used the old one are listed.

**Access and tokens**
50. A client or admin opens the status endpoint → `403 ROLE_NOT_ALLOWED`.
51. Owner fetches the attempt without the window token → state only, no question; `resume` gives a new token.
52. Leave sent during page unload (keepalive) is lost → re-sent from `sessionStorage` on reload; counted once.
53. Answer-key script run without `DEVSYNC_DEMO_TOOLS=1` or against a non-`_demo` database → refuses; the app exposes no answer-key route.

---

## 17. Tests (follow existing structure and gate; no thresholds lowered, no tests removed)

### 17.1 Unit (Python)
- Blueprint builder: no related skills; one and two related skills; ties; keyword boosts (none, many, capped); clamping and rounding to 500 bp (sum exactly 10,000); minimum 3 primary competencies; fewer than 4 → unavailable; allocation with min 1; difficulty mix satisfied; insufficient pool removal and restart; reasons text; fingerprint stability (whitespace/case changes, irrelevant text) and change (new keyword hits that move a weight bucket, different slot skill).
- Selection: allocation respected; no duplicates; recently-seen avoided then allowed; exposure preference; deterministic per seed; order rule; `SelectionUnavailable`.
- Scoring: every §16 scoring case; parity vectors (`backend/tests/fixtures/assessment_scoring_vectors.json`, ≥ 30 cases) shared with the SQL tests.
- Filtering: `NewcomerEvidence.assessment_passed` combinations; texts; relaxation unaffected; replication mode unaffected; all existing filtering tests still pass.

### 17.2 Property tests (hypothesis)
Blueprint weights always sum to 10,000, each in [1,000, 4,000], multiples of 500; allocation sums to `question_count`; determinism; scoring monotonic (one more correct answer never lowers the score); SQL and Python agree on random answer patterns (sampled into the shared vectors).

### 17.3 Database (integration, testcontainers)
All definer functions: wrong user, wrong token, not current question, after deadline (with/without grace), double answer, concurrent answers (one wins), concurrent starts (one wins), focus idempotency, termination at the limit, idempotent scoring, evidence written once, `times_served` incremented, immutability triggers (approved questions, blueprints), RLS cross-user checks, migration up/down.

### 17.4 API
Authorization matrix rows for every new route (anonymous, client, other developer, owner, admin); IDOR (other attempts → 404); every error code; rate limits; CSRF; idempotent start; contract (`check_openapi.py`); schemathesis on the new routes; response scan proving no answer data; bid creation `ROLE_ASSESSMENT_REQUIRED`; eligibility preview includes assessment status; admin void and re-evaluation.

### 17.5 Frontend (Vitest + RTL + MSW)
Status card in every state; consent required before Start; runner flow (answer, skip with confirm, finish early); keyboard 1–4 and Enter; countdown from server offset; `useFocusGuard` (hidden → leave; fullscreen exit → leave; blur < 3 s ignored; coalescing within 5 s; seq increments; offline queue); warning overlay; termination screen; `ATTEMPT_MOVED` screen; result view (no answers); draft preserved and restored; practice-test renaming; profile section; dark mode; reduced motion; a11y checks.

### 17.6 End-to-end (Playwright: Chromium, Firefox, WebKit, iPhone 14; run 3× at the gate)
1. **Newcomer pass:** Rafsan takes the assessment (answers from the `demo-answer-key` script spawned by the test), passes, bids, client sees the assessment line.
2. **Fail and retake lock:** a fresh newcomer answers wrongly (the test uses the answer-key script to pick wrong options deliberately) → not passed → card shows retake date → bid blocked.
3. **Two-leave rule:** start; trigger one leave (switch to a new page with `context.newPage()` + `bringToFront()`, or exit full screen with `document.exitFullscreen()` in Chromium) → warning; trigger a second → terminated screen; admin queue shows the flagged attempt.
4. **Debounce:** a blur shorter than 3 s (dispatch `blur` then `focus` quickly) → no leave.
5. **Reload and resume:** reload mid-attempt → one leave counted, same question resumes, deadline unchanged.
6. **Second window:** open the attempt in another page → first page shows "continued in another window".
7. **One-way:** browser Back during the attempt doesn't show previous questions; old question ids rejected (API check).
7a. **Practice isolation:** a practice test attempt never contains a question with `active = false`.
7b. **Void and retake:** admin voids Rafsan's attempt (with step-up) → his bid becomes ineligible with the voided text → he can start a new attempt immediately.
8. **Expiry:** with a test-only short time limit (settings override in the test environment), the timer reaches zero → scored result; and a variant where the page is hidden when time runs out, then shown → result appears immediately.
8a. **Esc and re-entry:** in Chromium, exit full screen via `document.exitFullscreen()` (Esc equivalent) → warning; re-entry refused (stub `requestFullscreen` to reject) → "Continue without full screen" works.
9. **Reuse:** pass for one project, open a second project whose React slot has the same fingerprint → status `PASSED` without a new attempt.
10. **Experienced developer:** no assessment section; bidding unchanged.
11. **Fallback:** a slot whose blueprint is unavailable shows the practice-test explanation.
12. **Mobile:** iPhone profile completes an attempt in focus layout; buttons reachable; no horizontal scroll.
13. **Demo 1 walkthrough** (§14.2) passes in `make demo-check DEMO=1`.
Visual baselines for: status card states, consent, runner (light/dark, 390/1440), warning overlay, result; accessibility scans (axe) on all of them.

### 17.7 Performance
Blueprint build < 50 ms; selection < 50 ms; start attempt end-to-end < 400 ms; answer < 200 ms (p95 on the dev machine); no N+1 queries on the status and bids endpoints (query-count assertions).

---

## 18. Documentation
- `docs/ROLE_ASSESSMENT.md`: purpose, principles, blueprint algorithm with a worked example, selection, scoring and pass rule, lifecycle, focus mode, reuse/retake/validity, fallback, integration with Algorithm 1 and reputation, limits, viva answers.
- `docs/ALGORITHMS.md`: add the blueprint, selection and scoring sections (DevSync extension, not PCS).
- `docs/USER_GUIDE_DEVELOPER.md` and `docs/USER_GUIDE_CLIENT.md`: short sections.
- `DECISIONS.md` (§3), `docs/FR_MAPPING.md` (new requirement IDs), `PROGRESS.md`, `docs/security-reviews/role-assessment.md`, and the hand-off document if handing over.

---

## 19. Implementation order (each step: build → tests → keep the gate green)

1. Audit and plan (§0).
2. Migration and models (§4) with downgrade; RLS; settings.
3. Competency catalogue, tagging of existing questions, writing **and self-verifying** all new questions **by you** (§13.3: execution checks with `make question-checks`, independent second solve, verification report), validation in `build_question_bank.py`, and the team review files prepared for after Demo 1.
4. Pure algorithms (§5) with unit and property tests.
5. DB functions (§10) with integration tests and scoring parity.
6. Services and API (§6, §8, §9) contract-first, with API and security tests.
7. Filtering and reputation integration (§8.2–8.4) with existing tests kept green.
8. Frontend (§11) and admin tools (§12) with unit, a11y and visual tests.
9. Seed and demo updates (§14), E2E (§17.6).
10. Full gate, `/security-review`, `make demo-check DEMO=1`, documentation, honest report.

If time runs short before 1 November: keep §6–§8 and §11 complete for the demo path; admin question-review UI (§12.2) and accommodations (§12.3) may move after Demo 1 (record in `PROGRESS.md`). Never ship without the server-side rules, focus mode, scoring parity and the E2E walkthrough.

---

## 20. Definition of done

- [ ] Every newcomer bidding for the same slot gets the same blueprint; blueprints are rule-based, explainable and frozen at publish.
- [ ] Question bank written and self-verified by Claude Code (execution checks for code questions, independent second solve for all), marked `SELF_VERIFIED` with a verification report; team review files ready for after Demo 1; questions only from the approved bank; no live AI.
- [ ] Overall timer (no per-question timers), one-way navigation, skip and finish early, all enforced on the server.
- [ ] Focus mode with consent, two-leave rule, debounce, coalescing, heartbeats, single-window tokens; iPhone fallback.
- [ ] Difficulty-weighted scoring with the pass rule; SQL and Python agree; terminated attempts can't pass.
- [ ] Results reusable by fingerprint for 180 days; retake every 30 days per fingerprint; one open attempt.
- [ ] Newcomer bids require a valid passing result (server-enforced); evidence linked to bids; Algorithm 1 otherwise unchanged; replication mode unchanged.
- [ ] Starting reputation unchanged in formula; newcomer status and exit unchanged.
- [ ] Practice tests renamed and still working, never showing role-assessment questions; profile shows role assessments clearly labelled.
- [ ] Demo answer key works on the production-mode demo stack as an operator-only command-line tool, with no app route.
- [ ] Client sees a scoped assessment line; admin can review flagged attempts and void with step-up.
- [ ] All corner cases in §16 tested; unit, property, DB, API, security, frontend, visual, a11y and E2E (4 browsers × 3) pass; `check_openapi.py`, `check_rls.py`, gate and `make demo-check DEMO=1` pass.
- [ ] Documentation and decisions updated; final report states exactly what ran and what's left.
