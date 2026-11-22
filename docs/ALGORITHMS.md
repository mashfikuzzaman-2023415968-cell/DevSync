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

## Worker filtering — Algorithm 1 + newcomer rule — Phase 5

**What it answers.** Of the sealed bids on a project, which developers are *eligible* to be on the
team, which are not and why, and which make each slot's shortlist for team formation. It is
[PCS] Algorithm 1 (§4.2) plus DevSync's newcomer rule, relaxation and advancement ordering
(`app/algorithms/filtering.py`, spec §9.2). Pure and deterministic; scores are on 0–1 (the UI shows
them ×100).

**Steps.**
1. **Paper constraints.** Keep bid *i* iff performance `P_i ≥ P0`, competency `C_i ≥ C0`, days
   `t_i ≤ T^d` (deadline), price `c_i ≤ C''_j` (budget after the platform fee). Comparisons use a
   tiny epsilon so a score **equal** to the threshold passes.
2. **Newcomer rule (ours).** A newcomer (fewer than `newcomer.threshold` completed projects) has
   the `P0` check replaced by "a passing skill test for the slot's skill" (evidence ≥
   `newcomer.pass_mark`); the `C0` check applies only if `filter.newcomer_competency_check` is on
   (their competency is built from starting values, so it's off by default).
3. **Other gates (ours).** Account active; the slot's skill is in the developer's skills;
   availability feasible (§9.17); no confirmed self-dealing flag with this client.
4. **Relaxation.** If there are fewer eligible bids than the team size, or a slot is short, relax
   `P0` and `C0` by 0.05 (up to 3 steps, never below 0), re-evaluating each time and reporting each
   step to the client ("Minimum performance relaxed from 45 to 40 to find enough candidates"). If
   still short → the too-few-bids flow (§9.19).
5. **Advancement + shortlist.** Order each slot's survivors by the client's choice — descending by
   P (Quality) or C (Balanced), ascending by days (Fast) or price (Budget) — and keep the top
   `K_s = max(3·count_s, 6)` as the shortlist for formation.
6. **Output.** `FilterResult(eligible, shortlisted, not_shortlisted, rejected_with_reasons,
   relaxations, too_few, shortfall)`. Reasons are stable codes — `LOW_PERFORMANCE`,
   `LOW_COMPETENCY`, `TOO_SLOW`, `OVER_BUDGET`, `NO_SKILL_EVIDENCE`, `SKILL_MISMATCH`, `UNAVAILABLE`,
   `SUSPENDED`, `SELF_DEALING`, `NOT_SHORTLISTED` — reported in a fixed precedence so a bid failing
   several gates always shows the same first reason.

`algorithm.mode = "pcs_replication"` switches off the newcomer rule and relaxation, leaving the
paper's filter, for the replication experiments.

### Worked example (the §18.4 Stage-1 seed — "Online ordering system")

Budget ৳120,000, deadline 30 days, four slots (React, FastAPI, PostgreSQL, Testing), **12 sealed
bids** with `P0 = 0.45`, `C0 = 0.40`. The filter returns **10 eligible and 2 ineligible**:

- **Shakib Hasan → `TOO_SLOW`** — bids 31 days, over the 30-day deadline.
- **Lamia Akter → `NO_SKILL_EVIDENCE`** — a newcomer bidding the FastAPI slot whose FastAPI role
  assessment was not passed ("Role assessment 50 — below the pass mark of 60").
- The other two newcomers pass the newcomer rule with a passed role assessment for their slot:
  **Nadia Rahman** (React) and **Mehjabin Chowdhury** (Testing). The seven experienced bidders
  clear `P0`/`C0`.

The seed asserts exactly these numbers and reasons, and the Phase 5 gate (`phase5_checks`) fails if
they drift.

## Role assessment — blueprint, selection, scoring (DevSync extension, not PCS)

The newcomer rule's evidence for a slot is a **role assessment** (`ROLE_ASSESSMENT_BUILD_SPEC.md`
§5; full description and a worked example in `docs/ROLE_ASSESSMENT.md`). Three pure modules:

- **Blueprint** (`algorithms/role_blueprint.py`):
  - **Competencies.** The slot skill's competencies (80 points) plus the core competencies of
    the two skills that share most milestones with it (20 points).
  - **Keyword boost.** Whole-word keyword hits in the project text add `min(hits, 5) × 4`.
  - **Choice and weights.** At most 6 competencies, at least 3 of them from the slot's skill.
    Weights are clamped to 10–40 % in 5 % steps and add up to exactly 100 %.
  - **Questions.** Allocated by largest remainder, with the 4/5/3 difficulty mix assigned to
    what the approved pool can supply.
  - **Fingerprint.** A SHA-256 of the canonical blueprint. Equal fingerprints mean a pass is
    reused.
- **Selection** (`algorithms/assessment_selection.py`): the exact allocation per competency
  and difficulty, preferring questions unseen for 180 days. It picks at random among the 5
  served least often (exposure control). The attempt opens on a medium question and alternates
  competencies.
- **Scoring** (`algorithms/assessment_scoring.py`, identical in SQL `role_score_core`):
  - **Weights.** Questions weigh easy 2, medium 3, hard 4.
  - **Per competency.** `floor(10000 × earned / possible)`.
  - **Overall.** `floor(Σ weight × score / 10000)`.
  - **Pass.** Overall ≥ 6000 bp and every competency of weight ≥ 2000 bp scores ≥ 4000 bp.
  - **Integer arithmetic only.** 35 shared vectors check Python against SQL.

Algorithm 1 takes the result as `BidInput.assessment_passed`: a newcomer passes the evidence
check only with `score ≥ newcomer.pass_mark` **and** a role assessment that wasn't failed.
Relaxation never relaxes it; `pcs_replication` has no newcomer rule.

## Reputation — [PCS] Eq. 1–12 — Phase 6

Code: `backend/app/algorithms/reputation.py` (one function per equation, `compute_snapshot()`
for a whole history), explanations in `reputation_explain.py`, review weights in `trust.py`.
Spec §9.1; mapping to the paper in `docs/PAPER_ALIGNMENT.md`.

**What it is for.** A developer's reputation answers two questions a client has when choosing a
team: *can this person do the work?* (**competency C**) and *how did their past projects go?*
(**performance P**). Algorithm 1 filters bids on both (C ≥ C₀, P ≥ P₀), and team formation
(Phase 7) uses C and teamwork in the fitness function.

**The six parameters, in plain words** (screens show them 0–100):

| Shown as | Symbol | Measures | Computed by |
|---|---|---|---|
| Expertise | ω | how varied your completed projects are | Eq. 1, Simpson's diversity over the domains of your projects: 1 − Σ n(n − 1) / (N(N − 1)) |
| Communication | X | check-ins, replies, accurate updates | Eq. 2, an exponentially weighted average: new = α × this project + (1 − α) × before (α = 0.7) |
| Teamwork | X_m | peers' ratings and help with blockers | Eq. 3, the same kind of average |
| Quality | β | clients' ratings, plus verified outside reviews | Eq. 5–6 average the ratings *within* a project (recent milestones weigh 0.7), Eq. 7–8 average *across* projects (older ones weigh 0.7, A6), Eq. 9 mixes internal 0.8 and external 0.2 |
| Client diversity | μ | whether different clients hire you | Eq. 10, Simpson's diversity over clients |
| Punctuality | T | time left before deadlines | Eq. 11: 1 − average of (days taken / deadline), each ratio capped at 1 so late work counts 0 (A2) |

Then **C = f·ω + (1 − f)·X** (Eq. 4, f = 0.7) and **P = g₁·β + g₂·μ + g₃·T** (Eq. 12,
0.5 / 0.25 / 0.25). All weights are platform settings (`rep.*`); the settings refuse κ ≤ 0.5,
α_x or α_e ≥ 0.5 and weights that don't add up to 1.

**Our extensions** (switched off by `algorithm.mode = pcs_replication`):
- *Newcomer starting values* (§9.1.3): before any project, X starts at 0.40 + 0.05 per verified
  item (phone, email, complete profile, verified certificate; max 0.60), ω at 0.2 per domain with
  a passed skill check (max 0.5), quality at the platform's average β, and teamwork, client
  diversity and punctuality at a neutral 0.5. The paper sets them to zero.
- *Change cap*: one project moves communication, teamwork or quality by at most 0.15 (counts and
  ratios — ω, μ, T — are never capped). Both the raw and the capped value are logged.
- *Trust-weighted reviews* (§9.14): a review from a new, unverified or flagged account weighs less.
- *Per-skill competency* C_{i,s}: competency with ω replaced by the share of projects in the
  slot's domain (D97).

**How it runs.** The history of completed projects (`reputation_history`; simulated in Phase 6,
real from Phase 11, D84) goes through `compute_snapshot()` project by project, oldest first. After
each project every parameter gets a log row (old, raw, new, inputs, reason code), which the
Reputation page turns into a sentence ("Punctuality 50 → 33: finished in 20 of 30 days.").
Re-running with the same history and settings adds nothing (idempotent).

### Worked example (two projects; the same numbers are asserted in `test_worked_example_two_projects`)

A newcomer with 3 verified items (Γ⁰ = 0.55) and a passed skill check in one domain (ω⁰ = 0.2);
quality without reviews = 0.6.

**Project A** — front-end, client c1, 20 of 30 days; communication rated 0.8, teamwork 0.7;
milestone rating 0.75 then final review 1.0.
- X = 0.7 × 0.8 + 0.3 × 0.55 = 0.725, but the cap allows at most 0.55 + 0.15 → **0.700**.
- X_m = 0.7 × 0.7 + 0.3 × 0.5 = **0.640**.
- Within-project quality I = 0.7 × 1.0 + 0.3 × 0.75 = 0.925 = λ; β would be 0.925 → capped at
  0.6 + 0.15 = **0.750**.
- One project only: ω stays ω⁰ = **0.2**, μ stays **0.5** (A9); T = 1 − 20/30 = **0.333**.

**Project B** — back-end, client c2, 33 of 30 days (late); communication 0.6, teamwork 0.9;
rating 0.5; one verified outside review 1.0.
- X = 0.7 × 0.6 + 0.3 × 0.70 = **0.630** (inside the cap).
- X_m = 0.7 × 0.9 + 0.3 × 0.64 = 0.822 → capped at **0.790**.
- λ = 0.3 × 0.5 + 0.7 × 0.925 = 0.7975 (older project weighs more); ε = 1.0;
  β = 0.8 × 0.7975 + 0.2 × 1.0 = **0.838**.
- ω = 1 − 0/2 = **1** (two different domains); μ = **1** (two different clients);
  T = 1 − (0.667 + 1)/2 = **0.167** (33/30 clipped to 1).
- **C = 0.7 × 1 + 0.3 × 0.63 = 0.889**; **P = 0.5 × 0.838 + 0.25 × 1 + 0.25 × 0.167 = 0.711**.

In `pcs_replication` the same history starts from zeros and has no cap: X = 0.588, X_m = 0.777,
β = 0.838, C = 0.876, P = 0.711 (`test_replication_full_example`).

### Does reputation track true ability? (E5, measured)

On simulated histories (seed 2026, 200 developers, 141 experienced), Spearman ρ between computed
P and latent quality is **0.797**, and between computed C and latent breadth + communication
**0.759** (test threshold 0.5; D96; details and the investigation note in `docs/SIMULATOR.md`).
Simulated data, not real users.

### Stage-2 demo values (computed, simulated histories; `stage2_reputation_golden.json`)

| Developer | Projects / clients | C | P | Story |
|---|---|---|---|---|
| Arif Hossain | 8 / 5 | 81 | 73 | strong, varied |
| Nusrat Jahan | 6 / 5 | 76 | 76 | strong |
| Imran Kabir | 7 / 1 | 76 | 53 | one client only: client diversity 0 |
| Shakib Hasan | 4 / 3 | 50 | 47 | often late: punctuality 9 |
| Rafsan Haque | 1 / 1 | 20 | 66 | newcomer, 1 of 3 projects |

Every bidder on the "Online ordering system" stays eligible, so the documented 10 eligible bids
hold in stage 2.

## Team formation — [PCS] Eq. 13–19, Algorithm 2 — Phase 7

Code: `backend/app/algorithms/fitness.py` (Eq. 17–19, feasibility, presets), `bpso.py`
(Algorithm 2 with repair, locks, archive, early stop, timeout), `exact_solver.py`, `fairness.py`,
`explain.py`, `formation.py` (one run end to end) and `baselines.py` (the greedy baseline). All
pure: no clock, I/O or database; randomness from a seeded `numpy.random.Generator`. Equation-level
mapping and the A3/A7/A10/A13 resolutions are in `PAPER_ALIGNMENT.md`.

### Fitness (Eq. 17–19)

For a team S: F(S) = Σ_{i∈S} (C1·C_i + C2·X_{m,i} − C3·t_i/T^d − C4·c_i/C), with the weights
normalised to sum 1, T^d the deadline in days and C the budget after the platform fee (A10). An
infeasible team scores −∞ (A3, D111). In `devsync` mode a team is feasible when it has exactly N
members, each slot exactly its count, no developer twice, Σ price ≤ C, every required skill held
and at least the dial's number of newcomers; in `pcs_replication` only Eq. 13 and distinct
developers apply (D114).

**Worked example** (`test_eq17_*`): weights 0.4/0.3/0.2/0.1, T^d = 30 days, C = ৳10,000.
A (C 0.8, X_m 0.6, 15 days, ৳3,000): 0.32 + 0.18 − 0.10 − 0.03 = 0.37. B (0.5, 0.9, 30 days,
৳5,000): 0.20 + 0.27 − 0.20 − 0.05 = 0.22. D (0.7, 0.4, 6 days, ৳1,000): 0.28 + 0.12 − 0.04 −
0.01 = 0.35. So F({A, B}) = 0.59 and F({A, B, D}) = 0.94.

### Binary PSO (Algorithm 2) and the repair operator

P = 30 particles, I = 200 iterations, z1 = z2 = 1.5, inertia 1.0 (A13), v_max = 4 (ours), bounds
[−1, 1], early stop after 40 iterations without improvement, a timeout (10 s by default, checked
once per iteration). Positions start Bernoulli(N/k), velocities U(b_l, b_u) (D111). Each new
position is repaired (ours; §9.3): fix slot counts by score, add newcomers to meet the dial,
drop the worst score per paisa until the budget fits, fill uncovered skills; locked members
(forced inclusion) are never removed. The archive keeps the best distinct feasible teams.

### Exact verification, fairness, explanations

When the problem has at most 18 candidates and 2,000,000 combinations, the exact solver
enumerates every team (per-slot combinations) and returns the best three; the result shows
"Optimal" or the gap. The fairness dial runs k = 0 and the requested k with the same seed; the
cost of fairness is (F0 − Fk)/|F0| (0 when the minimum isn't binding or F0 ≤ 0), falling back to
the largest feasible k. "Why this team?" lists coverage, budget and schedule shares, newcomers,
each member's contribution and the term that most separates it from the runner-up; the risk
chips are BUDGET_TIGHT (> 95 % of C), SCHEDULE_TIGHT (> 90 % of T^d), LOW_TEAMWORK (mean X_m <
0.5), SINGLE_POINT_SKILL and NEWCOMER_ON_CRITICAL_PATH. "Why not selected" gives the best team
with the bid forced in and its gap, the highest price (৳100 steps, 10-step binary search on
φ ∈ [0.5, 1]) at which the bid would be chosen — property-tested: applied and re-run, it is
chosen — and the main gap against the selected bid in its slot, with that bid's days and price
(never its owner).

### Measured (simulated data, 2026-11-22)

- **Optimality (E1, D112):** 298 solvable instances (8–18 candidates, teams of 3–6, three
  presets, both modes): PSO optimal in 98.3 %, mean gap 0.042 % (`scripts/e1_bpso_vs_exact.py`,
  `runs/experiments/e1.csv`). The unit test on 200 instances requires ≥ 95 % and ≤ 2 %.
- **Speed (`tests/perf/test_formation_perf.py`):** |S| = 200 candidates, N = 10: about 2.5 s per
  run on the development laptop (budget 5 s); the exact solver on 18 candidates: 0.04 s (budget
  3 s).
- **Greedy baseline (E3's, `baselines.greedy_team`: top C + P per slot within the budget):** on
  99 simulated jobs DevSync's best team scores higher than greedy's in 87 and ties in 12 (never
  lower), on average 12.7 % higher; it is also cheaper on average (৳2,646 less per team). With the
  dial at 1 DevSync's teams included 158 newcomers against greedy's 154.
- **Presets (D115):** each preset's team is never worse than Balanced's on its own term (tested on
  every instance); Budget is no dearer than Quality in 189 of 200 random instances and Quality at
  least as competent in 195.

### The seeded project (gate check, D116)

`backend/scripts/formation_check.py` builds the snapshot of the stage-2 "Online ordering system"
exactly as a client's run (Balanced, dial 1, seed 20261207) and checks the team against
`tests/fixtures/formation_expected_team.json`: it includes a newcomer, the exact solver confirms
it optimal, and the same inputs give the same team twice. The homepage's fairness figures
(`frontend/src/content/homepage-example.json`) come from the same run at dial 0, 1 and 2.
