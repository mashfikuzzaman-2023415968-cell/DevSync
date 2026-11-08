# Security review — Role assessment (newcomer role assessments, `main...role-assessment`)

- **Date:** 2026-10-29
- **Reviewer:** Claude Code (`/security-review` method on `main...role-assessment`). Each
  candidate was checked end to end against the RLS policy, the GRANTs, the SECURITY DEFINER body
  and the service-layer check; findings were filtered at confidence ≥ 8/10.
- **Scope:**
  - Migration `0011_role_assessment`: the new tables, their RLS, the role-attempt definers, the
    practice definers limited to `PRACTICE`, the replaced `public_developer_profile`, and
    REVOKE/GRANT.
  - The role-assessment and admin-assessment routes, services and repository.
  - The newcomer bid gate (`bids.assessment_evidence_id`) and the `assessment.take` policy.
  - The new test-only routes, the operator answer-key script and the demo seed.
  - The assessment runner, result and admin screens.
- **Tester's human check (spec §14.22):** _pending_.
  1. Take an assessment as a newcomer in one browser while signed in as a second developer in
     another, and confirm the second can't open the first one's attempt (404).
  2. Confirm that no response in the browser's network tab contains a correct answer.

Unresolved high findings: 0

## Result of the review

No high-confidence vulnerabilities were found.

| Area | Conclusion |
|---|---|
| Correct answers never leave the server | `role_current_question` returns only the position, the question text, the snippet, the options and the competency name, never `correct_index` or the explanation. The response models have no answer or correctness fields, and a result shows only per-competency and overall scores. The OpenAPI examples hold no keys. Per-question correctness is shown only in the admin attempt detail, behind `admin.access`. |
| Question bank | The 0004 policy (admin or SYSTEM only) still applies. The pool and count definers return ids, competency, difficulty, exposure and counts only. The practice definers (`attempt_questions`, `record_test_answer`, `score_test_attempt`) now accept `PRACTICE` attempts only, so a role attempt can't be read all at once or answered out of order through them. |
| Attempt ownership (IDOR) | The `assessment.take` policy allows developers only and returns 404 for another user's attempt. RLS lets only the owner, an admin or SYSTEM read `test_attempts`, and every definer locks the row with `user_id = app_uid()`. A replayed Idempotency-Key only resumes the caller's own attempt. |
| Window token | Each token is 256 bits from `secrets.token_urlsafe`, stored only as its SHA-256 hash. It is compared with `hmac.compare_digest` in the service and checked again in SQL. On rotation the old hash is retired, and that window then gets ATTEMPT_MOVED. The token is returned once and never kept in the idempotency record. |
| One-way answers and the deadline | `record_role_answer` accepts only the current question, and the choice must be 0–3. An earlier question gets NOT_CURRENT_QUESTION, and an identical retry gets DUPLICATE without changing anything. After the deadline plus 5 s grace the attempt is scored instead. All times come from the server clock. |
| Bid gate and evidence | The server alone sets `bids.assessment_evidence_id`, from a pass that belongs to the caller, matches the slot's blueprint and is neither voided nor expired. The bid schemas use `extra="forbid"` and have no such field. `skill_evidence` has no write policy for the web role: role evidence is written only by the scoring definer and voided only by the admin definer. Practice-test evidence and reputation domains ignore role rows, except valid passes. |
| SECURITY DEFINER hygiene | Every new function pins `search_path`. Internal helpers (`role_token_state`, `role_touch`, `role_score_core`, `role_own_attempt`) are revoked from PUBLIC and every runtime role. Public definers are granted only to the app and worker roles. The admin definers check `is_admin()` themselves. `create_slot_assessment` checks that the caller is the project's client or SYSTEM. None of the definers uses dynamic SQL. |
| RLS on the new tables | `competencies`, `assessment_blueprints`, `slot_assessments` and `user_accommodations` have ENABLE and FORCE. Blueprints are written only through a definer. Triggers make approved questions and blueprints immutable. Accommodations can be read by the owner or an admin and written only by an admin. |
| Admin actions | The routes need `admin.access`. Voiding an attempt and setting an accommodation also need a recent step-up, and the definers check `is_admin()` again. |
| Mass assignment and body size | `StartIn`, `AnswerIn`, `FocusEventIn` and `HeartbeatIn` forbid extra fields. Deadline, extra time, leave limit and validity come from settings and accommodations. Assessment routes refuse bodies over 2 KB. |
| Test-only routes and the answer key | `/__test__/…/answer-key` and `/__test__/…/role-evidence` are mounted only when `DEVSYNC_ENV=test`. `scripts/demo_answer_key.py` runs only on the host and has no HTTP route. It refuses to run without `DEVSYNC_DEMO_TOOLS=1`, inside a container, or against a database not named `*_demo`. |
| XSS | The new screens use no `dangerouslySetInnerHTML`, `innerHTML`, `eval` or `new Function`. Question text and code snippets are rendered as React text. The sessionStorage helper stores only two non-secret draft prefixes. |
| Public profile | It adds only valid, unvoided passes: label, score, date and expiry. It shows no project, failed attempts, flags or answers. |

## Developer SMS inbox (added after the review above; D76)

A small page and two routes (`/api/v1/dev-sandbox/sms`) that show the texts DevSync "sent", for
demos. It deliberately has no sign-in, so the fail-closed switch is the whole defence:

| Area | Conclusion |
|---|---|
| Never in a real deployment | Mounted only when `sms_sandbox_enabled` (development, test, or production with `DEMO_STACK`, which production validation allows only with a localhost origin). `create_app` raises if the router exists elsewhere; tests build a production-style app and get 404 for both methods. Nothing is recorded either, so a real deployment holds no copy of any code. |
| What it holds | Only the newest 100 texts for six hours, in Redis. Codes are 5-minute one-time codes of demo and test accounts. Real SMS content is never different from the code text the app already sends. |
| Input handling | The phone filter is validated (`^\+?[0-9 ]*$`, 20 characters) and the limit is 1–100; anything else is 422. Redis values are parsed as data and unreadable entries are skipped. The page renders every value as React text. |
| Abuse | `DELETE` needs the CSRF token like every unsafe request. The routes skip the global per-IP limit (the page polls) but exist only where they are mounted. |
| Residual risk (accepted, documented) | On the offline demo stack Nginx listens on all interfaces; the host-name check blocks casual access by IP, but a peer on the same network who forges the `Host` header could read demo codes. Fix if wanted: bind the demo's ports to 127.0.0.1. |

## Findings fixed during the build

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Medium | The internal definer helpers could be executed by the runtime roles (PostgreSQL grants EXECUTE to PUBLIC by default), so the web role could call the scoring core directly. | **Fixed:** REVOKE from PUBLIC and from the app, worker and read-only roles. A DB test proves the web role gets a permission error. |
| 2 | Low | Assessment request bodies were bounded only by the app-wide 256 KB limit. | **Fixed:** a 2 KB limit on every assessment route (spec §15). An API test shows 413 PAYLOAD_TOO_LARGE. |
| 3 | Low | Starting an attempt failed with a 500 because the integer arguments didn't match the definer's `smallint` parameters. This failed closed, with no exposure. | **Fixed:** the arguments are cast to `smallint`, and API tests cover start, resume and replay. |

## Known design limitations (accepted, documented in `docs/ROLE_ASSESSMENT.md`)

- Leaving the window is detected and reported by the browser, so a determined cheater with a second
  device isn't stopped. The rules aim to keep the assessment fair, not to proctor it.
- When a competency has a single question, its per-competency score shows whether that one
  question was right. The question itself is never named.
- The 113 legacy questions are also used in practice tests. A practice result shows only an
  aggregate score, under a 30-day retake limit, so it reveals no individual answers.
