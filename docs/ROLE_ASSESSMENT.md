# Role assessment for newcomers

DevSync judges developers on their record: past projects, reviews, punctuality (the PCS model).
A newcomer has no record, so the newcomer rule (spec §9.2) asks for evidence of skill instead.
Before this feature that evidence was a generic skill test, which is easy to question ("why
does a React quiz prove you can do *this* job?"). Now a newcomer who wants to bid for a role
takes a **role assessment** built from that role's needs. Everyone bidding for the same role
takes the same assessment, under the same rules.

Source of truth: `ROLE_ASSESSMENT_BUILD_SPEC.md`; decisions D71–D74 in `DECISIONS.md`.

## Principles

1. **Per role, not per person.** A blueprint depends only on the project and the slot, never on
   the candidate.
2. **No live AI.** Questions come only from the approved bank; nothing is generated during an
   assessment.
3. **Evidence, not reputation.** A result says what someone can do; it never counts as
   completed work and never changes newcomer status (fewer than 3 completed projects).
4. **Algorithm 1 stays in charge.** A pass satisfies the newcomer evidence check only. Deadline,
   budget, skill, availability and the other checks still apply. In `pcs_replication` mode there
   is no newcomer rule, so no assessment.
5. **Generic tests become practice.** They stay, and show on profiles as practice results.

## The blueprint (`app/algorithms/role_blueprint.py`)

When a project is published, each slot gets a blueprint: which competencies, their weights,
how many questions of which difficulty, the time limit (15 minutes for 12 questions) and the
pass rule. The rules are deterministic and versioned (`BLUEPRINT_ALGO_VERSION = 1`):

1. **Normalise the project text.** Title, summary, description and requirements are
   lowercased, with whitespace and control characters cleaned.
2. **Find related skills.** These are the two other skills that share most milestones with
   the slot's skill.
3. **List the candidates.** The slot skill's competencies, plus the related skills' core
   competencies. A competency without enough approved questions (4 by default) is left out.
4. **Award base points.** The slot skill's competencies share 80 points and the related ones
   share 20; with no related skills the slot skill gets all 100.
5. **Add keyword points.** Each competency's keywords are matched as whole words in the text,
   up to 3 per keyword, and earn `min(hits, 5) × 4` extra points.
6. **Rank and keep up to six.** At least three must come from the slot skill; fewer than four
   in total (or three from the slot skill) makes the blueprint *unavailable*.
7. **Set the weights.** Weights are in basis points, proportional to the points, clamped to
   10–40 % and rounded to 5 % steps. The sum is exactly 100 %; any rounding difference goes to
   the largest weight.
8. **Allocate questions.** Each competency gets questions by largest remainder, at least one
   each. The global mix (4 easy, 5 medium, 3 hard) is spread round-robin over what each
   competency's pool can supply, with one spare question.
9. **Explain and fingerprint.** Each competency carries plain reasons ("Core skill of this
   role (FastAPI)", "The requirements mention: login, roles"). The blueprint gets a label and a
   SHA-256 **fingerprint** of its canonical form.

Rounding to 5 % steps means a small text edit rarely changes the fingerprint. Two slots with
the same fingerprint share one blueprint, so a pass counts for both.

### Worked example: the seeded "Online ordering system"

The seeded text ("React front end, FastAPI back end, PostgreSQL, tested.") gives:

**FastAPI slot.** The text mentions "orders" (API design) and "postgresql" (databases).

| Competency | Weight | Questions (easy / medium / hard) | Why |
|---|---|---|---|
| API design and HTTP | 20 % | 2 (0/2/0) | Core skill of this role (FastAPI); the requirements mention: orders |
| Databases and ORM | 20 % | 2 (1/1/0) | Part of this role's skill; the requirements mention: postgresql |
| Async and performance | 15 % | 2 (1/0/1) | Part of this role's skill |
| Authentication and authorization | 15 % | 2 (0/2/0) | Core skill of this role |
| Error handling and debugging | 15 % | 2 (1/0/1) | Part of this role's skill |
| Validation and schemas | 15 % | 2 (1/0/1) | Core skill of this role |

**React slot.** No keyword hits. Six of the seven React competencies tie, and step 7 gives the
rounding difference (10 %) to the largest weight, breaking the tie by code. So *Accessibility*
gets 25 % and the others 15 % each. This follows spec §5.1 step 8 exactly. It is a quirk worth
a decision after Demo 1, for example splitting the difference evenly when all scores are equal.

## Questions and the bank

The question bank holds 370 questions over 8 skills, with 354 approved for role assessments
(D74). Questions are scenario, code-reading, bug-spotting and best-practice items, each with
four options and one answer.

- **Execution checks.** Every code question whose answer depends on what code does has an
  execution check (`make question-checks`). The check runs the snippet for real and proves
  the marked option right and every other option wrong.
- **Blind second solve.** Every question was solved again by a reviewer that never saw the
  answer.
- **Human review.** The team's review follows after Demo 1 (`docs/question-review/`).
- **Kept apart from practice.** New questions are never used by practice tests, so the
  practice tests don't reveal the assessment pool.

**Selection** (`assessment_selection.py`) picks each competency's questions per difficulty. It
prefers questions the candidate hasn't seen in 180 days, and picks at random among the five
served least often. The order opens with a medium question and alternates competencies.

## Scoring and the pass rule (`assessment_scoring.py`, and the same in SQL)

- **Question weights.** Easy 2, medium 3, hard 4. A skipped or unanswered question is wrong.
- **Per competency.** `score = floor(100 × earned / possible)`.
- **Overall.** The weighted mean of the competency scores, rounded down.
- **Pass rule.** Overall ≥ 60 **and** every competency weighing 20 % or more scores ≥ 40.
- **Ended early or voided.** Never a pass.
- **Parity.** Integers only. 35 shared vectors (`backend/tests/fixtures/`) prove that Python and
  SQL agree.

## Taking it

1. On the bid sheet, a newcomer who picks a role sees **Role assessment required**: the
   competencies with weights, "Why these?", 12 questions, 15 minutes.
2. **Consent.** The rules are shown and accepted before starting:
   - one question at a time, no going back;
   - full screen, where leaving full screen, the tab or the app counts as leaving;
   - the first leave is a warning and the second ends the attempt;
   - only leaving is recorded, never the screen, camera or keystrokes.
3. **The runner.** It shows only the current question, with a countdown from the server's
   clock (amber under 2 minutes, rose under 30 seconds). Answers lock as they're confirmed.
   Skip asks first. "Finish now" ends early.
4. **The result.** Score, passed or not, each competency's score and weight, and the strongest
   and weakest. It shows the valid-until date or the retake date, and never the answers.

**The server decides everything.**

- **Time.** The deadline is fixed at start, with 5 s of grace for answers in flight. Any
  request about an expired attempt scores it first; a job scores abandoned ones.
- **One-way navigation.** Only the current question is served, and an answer for any other
  question is refused.
- **Window token.** Each window gets a 256-bit token, stored hashed and compared in constant
  time. Resuming elsewhere issues a new one, and the old window shows "continued in another
  window".
- **Single attempt.** One open attempt of any kind at a time, enforced under a per-developer
  lock.

## Reuse, retakes, validity

| Rule | Value |
|---|---|
| A pass counts for | Any slot with the same fingerprint, for **180 days** |
| Retake | One scored attempt per fingerprint per **30 days** (ended attempts count; voided ones don't) |
| A bid placed with a valid pass | Stays linked to it, even after it expires (unless voided) |
| No assessment available for the slot | The practice-test result for the slot's skill is used, and the bid sheet says so |

## Bidding and Algorithm 1

- **Bid gate.** A newcomer's bid is refused without a valid pass (`409
  ROLE_ASSESSMENT_REQUIRED`). The server links the evidence to the bid.
- **Newcomer check.** Algorithm 1's newcomer check becomes "score ≥ pass mark **and** the role
  assessment wasn't failed". The reason code stays `NO_SKILL_EVIDENCE`, with plain texts such
  as "Role assessment 54 — below the pass mark of 60". Relaxing the minimums never relaxes the
  assessment.
- **Client view.** The client sees a line per newcomer bid ("Role assessment: 78, passed;
  strongest: …; weakest: …; taken 28 Oct"), never answers, focus events or flags.
- **Starting expertise.** It counts a domain with a valid pass. The formula is unchanged.

## Admin tools

- **Review queue.** Flagged attempts (ended under the two-leave rule, or offline for more than
  2 minutes). The detail view shows focus events, gaps and per-question correctness and
  response times.
- **Void.** Needs a fresh authenticator code and a reason. The evidence stops counting, affected
  bids are re-evaluated and their bidders told, and an immediate retake is allowed.
- **Mark reviewed.**
- **Extra time.** 25 % or 50 % per developer (step-up); API only for Demo 1.
- **Question bank.** List, approve (human review) and retire, never below a practice test's
  question count; API only for Demo 1.

## Honest limits

- **Browser-side detection.** Leave detection runs in the browser. A technical user can bypass
  it, and a second device can't be detected. The guarantees are server-side: the deadline,
  one-way navigation, hidden answers and single-window tokens. The assessment opens the door;
  real project evidence decides the rest.
- **Question review.** For Demo 1 the questions are self-verified, by execution and an
  independent blind solve. The team's human review follows; then
  `assessment.require_human_review` is switched on, and only human-approved questions are used.
- **Expiry in the browser tests.** Expiry is tested at the API level, by moving an attempt's
  deadline in the database. The shortest allowed time limit is 5 minutes, too long for a browser
  test.

## Viva answers

- **"Is it fair?"**
  - **Same assessment.** Everyone bidding for a role gets the same competencies, weights,
    question counts per difficulty, time and pass rule.
  - **Explained weights.** The weights come from the project's own text and plan, and each
    competency says why it's there.
- **"Can't someone cheat?"**
  - **What the server guarantees.** The server keeps the answers, the clock and the order.
    One window at a time, and nothing is answered out of order.
  - **What leave detection is.** Leaving is detected and limited, honestly disclosed as
    browser-side.
- **"Does passing make you experienced?"** No. It only opens the newcomer door for that kind of
  role. Reputation still comes from completed work.
- **"Did an AI write the questions?"**
  - **Writing and checking.** Claude Code wrote and verified them: execution checks for code,
    and an independent blind solve for every one.
  - **No live AI.** Nothing is generated at runtime.
  - **Human review.** The team reviews them after Demo 1.
