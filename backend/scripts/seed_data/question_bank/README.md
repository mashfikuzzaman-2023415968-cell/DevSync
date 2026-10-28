# Question bank — how to write and check questions

One YAML file per skill (`react.yaml`, `fastapi.yaml`, …). Each file has the skill's
**competency catalogue** and its **questions**. `make question-bank` validates everything and
writes `backend/alembic/seed/question_bank_v2.json`; `make question-checks` runs every code
question for real. Rules come from `ROLE_ASSESSMENT_BUILD_SPEC.md` §13.

## Question fields

```yaml
- id: fastapi-authn-authz-07          # stable slug: <skill>-<competency with dashes>-NN; never reused
  competency: authn_authz             # a code from this file's catalogue
  difficulty: 2                       # 1 easy (recall, simple use) · 2 medium (apply to a scenario)
                                      # · 3 hard (combine ideas, subtle bugs)
  text: "A login endpoint returns 200 for a wrong password. Which line causes it?"
  code_snippet: |                     # optional, plain text, ≤ 25 lines, ≤ 1,500 characters
    1  @app.post("/login")
    2  def login(body: Login):
  options:                            # exactly 4, distinct, single correct answer
    - Line 1
    - Line 2
    - Line 3
    - Line 4
  correct_index: 2                    # 0–3
  explanation: "…"                    # ≤ 600 characters, for admins (never shown to candidates)
  check: execution                    # code questions only: execution | manual
  status: DRAFT                       # DRAFT until verified; APPROVED is set by the review tool
  source: CLAUDE_GENERATED            # HUMAN for the 128 legacy questions
  active: false                       # practice-test flag: legacy true, new questions false
  review_level: NONE                  # set by the review tool (SELF_VERIFIED) or the team
  reviewed_by_name: null
  reviewed_at: null
  verification: null                  # written by the review tool
```

Legacy questions (`*-legacy-NN`) must keep `text`, `options`, `correct_index` and `difficulty`
exactly as they are: migration 0011 finds them in the database by text. Give each one a
`competency` and an `explanation`. If a legacy question is ambiguous or weak, leave it as it is
(it stays a practice question and stays `DRAFT` for role use) and write a better new question
instead.

## Quality rules (§13.2–13.3)

- One unambiguous correct answer; three plausible distractors (a competent developer who has a
  specific misconception would pick them); no trick wording; never "all/none of the above" or
  "both"; no "Which is NOT…" unless the negation is unmistakable.
- Styles: scenario ("A list re-renders on every keystroke. Most likely cause?"), code reading
  ("What does this print?"), bug spotting ("Which line causes the bug?" with numbered lines),
  best practice and security. Aim for about a third code questions in each competency.
- Options roughly the same length and form; the correct one must not be the longest by habit.
- Spread `correct_index` evenly over 0–3 within the skill.
- No near-duplicates of other questions in the bank (the build compares normalised texts).
- Facts must hold for current stable versions (React 18, FastAPI 0.11x with Pydantic v2,
  PostgreSQL 16, pytest 8, Node 20, Playwright 1.4x+). Avoid version trivia.

## Execution checks

A question whose answer depends on what code does (output, return value, error, which line is
wrong) is `check: execution` and has `backend/scripts/question_checks/<skill file stem>/<id with
underscores>.py`:

```python
def check(ctx, q):
    out = ctx.python("print(sorted({3, 1, 2}))")
    ctx.expect_only(q, out)       # marked option == output; no distractor equals it
```

`ctx.python(code)`, `ctx.python_status(code)`, `ctx.node(code)` (React/react-dom/jsdom available
via `require`, no JSX — use `React.createElement`), `ctx.node_status(code)`, `ctx.sql(script)`
(fresh schema on PostgreSQL 16; rows of the last statement), `ctx.sql_error(script)` (SQLSTATE or
None), `ctx.expect_only(q, actual)`. For bug-spotting, run the buggy code and show it fails, then
run it with the marked line fixed and show it passes, and with each other line "fixed" in the
obvious way and show the bug remains. A check must prove the marked option right **and** every
distractor wrong. Questions whose answer can't be shown by running code are `check: manual`.

Run `make question-checks ONLY="id1 id2"` while writing, and `make question-bank` to validate.
