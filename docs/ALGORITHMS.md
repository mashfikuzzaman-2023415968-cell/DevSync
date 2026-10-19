# ALGORITHMS

Plain-English explanations of DevSync's algorithms, written as each phase builds them. The pure
implementations live in `backend/app/algorithms/` (no database, network or clock; seeded RNG;
typed and tested). Formulas follow spec §9; the paper is Akter et al. 2023 [PCS].

## Critical Path Method (CPM) — Phase 4

**What it answers.** Given a project's milestones, how long each takes, and which must finish
before which, CPM computes the shortest possible project duration and shows which milestones have
no room to slip (the *critical path*). It is the engine behind the create-project plan preview and
the plan page (`app/algorithms/cpm.py`, spec §9.10).

**Inputs.** A list of milestones, each with a duration in days and a set of predecessors
(finish-to-start: a milestone can start only once all its predecessors have finished). Durations
are whole days; dependencies form a directed graph.

**Steps.**
1. **Reject cycles.** A depth-first search (three-colour: white/grey/black) looks for a back edge.
   If milestone A depends on B which depends back on A, there is no valid schedule, so the API
   returns `422` with the cycle spelled out (`A → B → A`) instead of a plan.
2. **Order the work.** A Kahn topological sort puts the milestones in an order where every
   milestone comes after all of its predecessors.
3. **Forward pass** (earliest times). Walking that order, each milestone's **earliest start (ES)**
   is the latest earliest-finish of its predecessors (0 if it has none); its **earliest finish
   (EF)** is `ES + duration`. The project **duration** is the largest EF.
4. **Backward pass** (latest times). Walking the order in reverse, each milestone's **latest
   finish (LF)** is the smallest latest-start of its successors (the project duration if it has
   none); its **latest start (LS)** is `LF − duration`.
5. **Slack and the critical path.** **Slack = LS − ES = LF − EF**. A milestone with zero slack is
   *critical*: any delay to it delays the whole project. The chain(s) of critical milestones from
   a start to the finish are the critical path(s); the algorithm returns **all** of them, not just
   one (ties are real and worth showing).
6. **Calendar dates** (optional). Given a start date, `schedule_dates` turns the day offsets into
   real dates for the Gantt chart. Times are day offsets; the UI renders them in Asia/Dhaka.

**Output.** For each milestone: ES, EF, LS, LF, slack and whether it is critical; plus the total
duration and every critical path. The result is deterministic — the same plan always produces the
same schedule — so it is safe to store as a baseline at publish time.

### Worked example (spec §18.2 — "Online ordering system")

Six milestones:

| Milestone | Days | Must finish after |
|---|---|---|
| Requirements | 4 | — |
| Database | 5 | Requirements |
| Backend API | 8 | Database |
| Frontend | 5 | Database |
| Integration | 3 | Backend API, Frontend |
| Testing | 4 | Integration |

CPM gives a **duration of 24 days**. The **critical path** is
`Requirements → Database → Backend API → Integration → Testing` (all slack 0). **Frontend has
4 days of slack**: it needs only 5 days but Backend API (its sibling before Integration) needs 8,
so Frontend can start or finish up to 4 days later without moving the deadline. This is the exact
case the plan preview draws — Frontend's bar in accent with a lighter 4-day slack tail, everything
else in rose — and it is asserted byte-for-byte in `tests/algorithms/test_cpm.py` and
`tests/security/test_projects.py`.

**Performance.** The passes are linear in milestones + dependencies; a 300-milestone plan computes
in under 50 ms (perf test), so the preview can run live as the client edits.

## Schedule forecast — Phase 4

`app/algorithms/forecast.py` (spec §9.10 step 5) projects a finish date for a project already under
way. Each milestone contributes progress by task state — TODO 0, IN_PROGRESS 0.5, REVIEW 0.85,
DONE 1 (`milestone_progress`) — and the forecast compares work done against the baseline schedule
to estimate the remaining duration and whether the project is ahead of or behind plan. Pure and
deterministic; it drives the workspace forecast chip in later phases.
