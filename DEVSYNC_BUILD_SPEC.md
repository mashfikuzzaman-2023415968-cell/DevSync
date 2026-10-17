# DevSync — Complete Build Specification for Claude Code

**Plan the project, hire a fair team, monitor the work, learn from it.**

A production-grade web platform for collaborative software crowdsourcing: clients plan software projects (Critical Path Method), DevSync forms fair, balanced teams of freelance developers (reputation-aware binary Particle Swarm Optimization), monitors the work through milestones and evidence, pays through simulated milestone escrow, and feeds what actually happened back into each developer's reputation so the next team is chosen more fairly.

**Research basis (implemented, then extended):**

1. Akter, S.N., Sinthia, A.K., Roy, P., Razzaque, M.A., Hassan, M.M., Pupo, F., Fortino, G. (2023). *Reputation aware optimal team formation for collaborative software crowdsourcing in industry 5.0.* Journal of King Saud University – Computer and Information Sciences, 35(8), 101710. — referred to below as **[PCS]** (the paper calls its system "PCS").
2. Rahman, S.T., Sinthia, A.K., Akter, S.N., Roy, P., Razzaque, M.A. (2021). *Reputation Aware Fair Worker Selection in Collaborative Software Crowdsourcing.* STI 2021, Dhaka (the preliminary version of [PCS]).

Course context: **CSE 3102: Software Design and Development Project**, Department of CSE, University of Dhaka. Supervisor: Palash Roy. Team: Mashfikuzzaman Taeen (Team leader), Salwa Baki (Backend developer), Raisa Tabassum (Frontend developer), Sara Binte Shafayet (Tester). The four official roles are **Team leader** (coordination + research algorithms: reputation, filtering, PSO, CPM, experiments), **Backend developer**, **Frontend developer** and **Tester** (test automation, security checks, performance tests, deployment).

---

## Table of contents

- [0. How Claude Code must use this document](#0-how-claude-code-must-use-this-document)
- [1. Product summary](#1-product-summary)
- [2. Roles and permissions](#2-roles-and-permissions)
- [3. Technology stack](#3-technology-stack)
- [4. Repository layout](#4-repository-layout)
- [5. Architecture](#5-architecture)
- [6. Configuration and platform settings](#6-configuration-and-platform-settings)
- [7. Data model](#7-data-model)
- [8. State machines](#8-state-machines)
- [9. Algorithms (exact)](#9-algorithms-exact)
- [10. API specification](#10-api-specification)
- [11. Background jobs and schedules](#11-background-jobs-and-schedules)
- [12. Notifications and email catalogue](#12-notifications-and-email-catalogue)
- [13. UI and UX specification](#13-ui-and-ux-specification)
- [14. Security architecture](#14-security-architecture)
- [15. Performance, reliability and scalability](#15-performance-reliability-and-scalability)
- [16. Testing strategy and the phase gate](#16-testing-strategy-and-the-phase-gate)
- [17. Build phases](#17-build-phases)
- [18. Seed data and the market simulator](#18-seed-data-and-the-market-simulator)
- [19. Experiments and evaluation](#19-experiments-and-evaluation)
- [20. Deployment and operations](#20-deployment-and-operations)
- [21. Documentation deliverables](#21-documentation-deliverables)
- [22. Definition of done](#22-definition-of-done)
- [23. Open questions for the supervisor](#23-open-questions-for-the-supervisor)
- [24. First message to the student](#24-first-message-to-the-student)

---

## 0. How Claude Code must use this document

You (Claude Code) are building the entire DevSync platform described here. This file is self-contained: everything you need is in it. Read sections 0–1 completely before anything else; then, for each phase, read that phase in section 17 plus every section it references.

### 0.1 Plan Mode workflow (mandatory for every phase)

1. **Start each phase in Plan Mode** (the student switches it on with Shift+Tab until "plan mode on" is shown; if it isn't on, ask the student to turn it on before you begin).
2. In Plan Mode, read the phase section and every referenced section (and, for any frontend work, load the skills in §0.4), then produce a **written plan** (listing the skills loaded): files to create or change, order of work, database migrations, API endpoints, screens, security controls from §14.13 for this phase, tests to write (by layer), commands the gate will run, and risks or open questions.
3. Save the plan to `docs/plans/phase-NN.md`, present a short summary to the student, and **wait for approval**.
4. After approval, the student exits Plan Mode; implement exactly the approved plan. If you must deviate, record it in `DECISIONS.md` and tell the student.
5. Finish the phase with the **phase gate** (§16.5): `make gate PHASE=N`. A phase is done only when it prints `PHASE N GATE: PASS`.
6. Update `PROGRESS.md` (current state, built, tested, known issues, gate table, session log; §0.5); if the person is handing over after this phase, write the hand-off document (§0.5), commit as `phase-N: <summary>`, tag `phase-N`, then **stop** and give the student: what was built, how to try it (exact commands and URLs), what to check by hand, and the gate table. Wait for "continue".

### 0.2 Working rules

1. **Phase order is strict** (Phase 0 → Phase 15). Never start a phase before the previous gate passes.
2. **Security is part of every phase**, never a final step. §14.13 lists which controls each phase must implement and test. Never weaken a security default to make a test or demo easier; use fixtures or an explicit `DEVSYNC_ENV=development` behaviour instead.
3. **Fail closed.** If validation, authentication, authorization, integrity or configuration checks fail, reject and log; never continue silently.
4. **Deny by default.** Every endpoint requires authentication unless listed as public in §10; every object access goes through the central authorization policy (§14.5).
5. **No happy-path-only tests.** Every component's tests include invalid input, boundaries, permission failures and failure cases.
6. **Never invent research results.** Experiment numbers in any document come only from `make experiments` outputs. Simulated data is labelled simulated everywhere.
7. **The paper's formulas are implemented exactly as written in §9**, with every ambiguity resolved by a documented, configurable default (§9.0, §23). Never change a paper formula silently; extensions live in separate, clearly named functions.
8. **The student must be able to explain every line.** Write docstrings for every module, class and public function; comment the *why* of every security, concurrency, money and algorithm decision. Prefer readable code over clever code. Keep `docs/ALGORITHMS.md` in plain English.
9. **Keep `algorithms/` pure:** no database, web framework, network or clock access; deterministic given a seed; typed; fully tested.
10. **Money is integer paisa** (`BIGINT`, 1 BDT = 100 paisa) when stored, sent or displayed. **Calculations** that need fractions or exponentials (fees, splits, rewards, penalties) use Python's `Decimal` (`backend/app/core/money.py`, a fixed context: precision 28, `ROUND_HALF_EVEN` for intermediate steps) and convert to paisa **once**, at the end, with an explicitly stated rounding mode (§9.12.1). Floats are never used for money anywhere (backend, frontend, tests); the frontend only formats integers it receives.
11. **All times are stored in UTC** (`timestamptz`) and displayed in `Asia/Dhaka`.
12. **Never log secrets** (passwords, tokens, OTPs, session ids, TOTP secrets, API keys, full phone numbers).
13. **Token hygiene:** read only the sections you need; don't paste large files or full test logs into the conversation; summarize. Start a fresh session (`/clear`) at each phase and resume from `PROGRESS.md` and `docs/plans/`.
14. **Ask, don't guess,** when the spec is ambiguous or contradicts itself. Record the answer in `DECISIONS.md` (date, decision, reason, alternatives considered).
15. **Design skills:** in Phases 0–1 frontend tasks load `frontend-design` (the `devsync-ui` skill doesn't exist yet); from Phase 2, once `devsync-ui` has been created, every frontend task loads both `devsync-ui` and `frontend-design` first, and 3D work also loads the `threejs-*` skills (§0.4). Never build a screen without them.
16. **Dependencies:** pin exact versions in lock files; add a new runtime dependency only if the spec names it or you record a decision for it.
17. **Out of scope** (do not build): real payment gateways, native mobile apps, screenshot/keystroke/time tracking, real-time video/voice, ML model training, non-software domains.

### 0.4 Claude Code skills (install in Phase 0; use from Phase 2 onwards)

These skills give Claude Code expert design and 3D knowledge so the whole app looks consistent, professional and impressive without the student having to repeat design instructions. Install them **at project level** (inside the repository's `.claude/skills/`, committed to git) so every team member's Claude Code uses the same ones.

| Skill | Purpose | Link | How to install |
|---|---|---|---|
| **frontend-design** (Anthropic, official) | A design discipline Claude applies before writing UI: bold but intentional typography, layout, colour and motion choices; avoids generic "AI-looking" interfaces | https://github.com/anthropics/skills/tree/main/skills/frontend-design (plugin version: `anthropics/claude-plugins-official`) | Either run in Claude Code: `/plugin marketplace add anthropics/claude-plugins-official` then `/plugin install frontend-design@claude-plugins-official`; **or** (preferred, so it is versioned with the repo) copy the `skills/frontend-design` folder from the link into `.claude/skills/frontend-design/` |
| **threejs-skills** (CloudAI-X, community) | Three.js knowledge (scene setup, cameras, lights, materials, animation, shaders, performance), audited by its authors against Three.js r160+ | https://github.com/CloudAI-X/threejs-skills | Clone the repository, review it (see below), and copy its skill folders (each one contains a `SKILL.md`) into `.claude/skills/` (for example `.claude/skills/threejs-fundamentals/`) |
| **devsync-ui** (project skill, created by Claude Code in Phase 2) | DevSync's own design system as a skill: tokens, typography, motion catalogue, component patterns, page-header pattern, quality bar, microcopy rules and the 3D rules of §13.12 | `.claude/skills/devsync-ui/SKILL.md` in this repo | Generated in Phase 2 from §13 (use the built-in `skill-creator` skill to structure it); updated whenever the design system changes |

**Rules for using skills**
1. **Phases 0–1:** frontend work loads `frontend-design` only, because `devsync-ui` is created in Phase 2; screens built in Phase 1 are restyled in Phase 2 anyway. **From Phase 2 on,** every frontend task (any phase that builds or changes screens) starts by loading `devsync-ui` and `frontend-design`. Where they disagree, **`devsync-ui` wins**, because it encodes this spec's design decisions; `frontend-design` supplies taste and polish within those rules.
2. **3D work** (the homepage hero and still renders, §13.12) also loads the relevant `threejs-*` skills. The 3D rules in `devsync-ui` and §13.12 override any skill advice about libraries, asset loading or performance (for example, no remote HDR environments, no external models).
3. **Security of third-party skills:** skills are instructions and may include scripts. Before installing, the student (with Claude Code's help) reads every `SKILL.md` and script, rejects anything that downloads code at runtime, needs unrelated API keys or changes security settings, and records the reviewed **commit hash** of each skill in `DECISIONS.md`. Skills are updated only deliberately, by repeating the review.
4. Claude Code lists the skills it loaded at the start of each frontend plan (`docs/plans/phase-NN.md`), so the student can confirm they were used.

### 0.5 Team hand-offs (sequential phase ownership)

The team builds DevSync **sequentially**: one person works through a run of consecutive phases, then **hands over** to the next person, who **continues from exactly where the previous person stopped**, as recorded in `PROGRESS.md`. The number of phases each person takes is not fixed in advance; it is decided by the team and recorded in `docs/OWNERSHIP.md` at each hand-off. Each person uses their own Claude Code with the same repository. These files and rules make every hand-off smooth.

**Files**

| File | Updated | Content |
|---|---|---|
| `PROGRESS.md` | After every working session and every phase | Top section **"Current state"** (current owner, current phase, last gate result, what is in progress, the very next step) followed by a **phase table** (phase, owner, status, gate result, date, tag) and a **session log** (date, person, what was done, what's next, blockers), newest first |
| `docs/OWNERSHIP.md` | At each hand-off | Who worked on which phases (filled in as the project goes), hand-off dates, and how to contact each person for questions |
| `docs/handoffs/handoff-NN-<from>-to-<to>.md` | Written by the outgoing person's Claude Code when they hand over; reviewed by both people | The hand-off document (template below) |
| `DECISIONS.md` | Whenever a decision is made | Every decision, deviation and spec clarification, so the next owner doesn't undo them |
| `docs/plans/phase-NN.md`, `docs/security-reviews/phase-NN.md`, `runs/gates/phase-N.json` | Each phase | Plan, security review and gate result of each phase |

**Hand-off document template** (`docs/handoffs/handoff-01-taeen-to-salwa.md`, etc.)
1. **Summary:** phases completed by the outgoing person, the **exact point where work stops** (last phase whose gate passed, plus anything started in the next phase), git tag of the last passing gate, overall status in two or three sentences.
2. **How to run it from scratch:** exact commands on a clean laptop (`git clone`, `make env`, `make certs`, `make up`, `make migrate`, `make seed-demo STAGE=N`), demo accounts and where their passwords come from, URLs to open.
3. **What exists:** modules, endpoints, screens, database tables and migrations added by the outgoing person, with file paths.
4. **Test and gate status:** last gate table, coverage, any skipped or flaky tests (there should be none) and why.
5. **Known issues and limitations:** with the files involved and suggested fixes.
6. **Open decisions and questions:** anything not yet decided (including answers still awaited from the supervisor).
7. **Things the next phases depend on:** contracts, APIs, seed data, settings and design-system pieces the next owner will build on; anything that must not be changed without care.
8. **Gotchas:** surprises, tricky areas, environment quirks.
9. **Read first:** the five or so files and spec sections the next owner should read before starting.
10. **Secrets and setup:** which `.env` values each person must generate themselves (`make env`) and which shared values (e.g. a GitHub token) are passed privately, never through git.

**Hand-off procedure**
1. The outgoing person finishes the phase they are on (gate PASS, security review done, `PROGRESS.md` updated, git tag `phase-N` pushed). Hand-overs happen **between phases**, never in the middle of one, unless the team agrees otherwise and the hand-off document says exactly what is half-done.
2. Their Claude Code writes the hand-off document; the outgoing owner checks it is accurate.
3. A short **hand-off meeting (about 30 minutes):** both people walk through the document; the incoming person runs the app from scratch on their own laptop using section 2 and confirms the last gate passes on their machine (`make gate PHASE=N`).
4. `docs/OWNERSHIP.md` and the "Current state" in `PROGRESS.md` are updated with the new person and the phase they start from; the new person continues from that point.
5. The outgoing owner stays available for questions during the next phase.

**Starting a session (every person, every time)**
Claude Code's first actions in any new session are: read `CLAUDE.md`, the "Current state" in `PROGRESS.md`, the latest hand-off document, `DECISIONS.md` (recent entries) and the plan of the current phase; run `git pull`, `make up` and `make migrate`; then summarize the current state and the next step to the person before doing anything else. `CLAUDE.md` contains this instruction so it happens automatically.

**Ending a session**
Before stopping, Claude Code commits work in progress to the phase branch (never leaving uncommitted changes), adds a session-log entry to `PROGRESS.md` (done, next, blockers), and updates "Current state", so the next session (by the same or another person) starts without guesswork.

**Early starts during a hand-off** (overlaps allowed by the phase dependencies, e.g. a phase whose prerequisites have already passed their gates): work on a separate branch, merge only after the earlier phases' gates pass, and note the overlap in `PROGRESS.md`.

### 0.3 Files you maintain throughout

| File | Purpose |
|---|---|
| `CLAUDE.md` | Short (≤ 60 lines) working rules + commands + pointer to this spec + the session start/end routine of §0.5; created in Phase 0 |
| `DEVSYNC_BUILD_SPEC.md` | This file (never edit except to fix agreed mistakes; record such fixes in DECISIONS.md) |
| `PROGRESS.md` | "Current state", phase table, gate results, session log, known issues, next steps (structure in §0.5) |
| `docs/OWNERSHIP.md`, `docs/handoffs/` | Phase ownership and hand-off documents between team members (§0.5) |
| `DECISIONS.md` | Every deviation, ambiguity resolution and dependency choice |
| `docs/plans/phase-NN.md` | The approved plan of each phase |
| `docs/BACKLOG.md`, `docs/sprints/sprint-NN.md` | Agile backlog and weekly sprint plans, reviews and retrospectives (§17.1) |
| `docs/ALGORITHMS.md` | Plain-English explanation of every algorithm with worked examples |
| `docs/PAPER_ALIGNMENT.md` | Equation-by-equation mapping of [PCS] to code, with deviations |
| `docs/SECURITY.md` | Threat model, controls, residual risks, OWASP checklist |
| `docs/TESTING.md` | How to run each test layer; latest gate results |
| `docs/API.md` | Pointers to OpenAPI plus worked examples |
| `docs/DEPLOYMENT.md` | Deployment, backups, restore drill, runbook |
| `docs/UI_GUIDE.md` | Design tokens, components, motion rules (generated from §13) |
| `docs/FR_MAPPING.md` | Mapping between the requirement IDs in this spec and the IDs in the submitted proposal (the proposal is a trimmed, renumbered subset; e.g. proposal FR-TEAM-3 = spec FR-TEAM-4). This spec is the full, authoritative feature list; the proposal is never a reason to drop a feature. Test names use the spec IDs; the mapping lets the student answer viva questions using the proposal numbering |
| `docs/papers/` | The student places the [PCS] paper PDF here (`akter2023-pcs.pdf`). §9 of this spec is authoritative; use the PDF only to check wording and notation, and record any mismatch in DECISIONS.md instead of silently changing a formula |
| `docs/design/` | The student's proposal, use case diagram and Gantt chart (for reference); generated ERD and architecture diagrams |
| `runs/demos/` | Demo readiness reports (§17.0) |

---

## 1. Product summary

### 1.1 The problem

1. **Newcomer trap:** freelance platforms rank developers by past reviews, so skilled newcomers rarely get a first project and never build a record.
2. **Individuals, not teams:** clients are handed individuals and must assemble and coordinate a balanced team themselves.
3. **Disconnected tools:** hiring platforms don't plan or track work; project tools don't form teams. What happens during a project never reaches reputation.
4. **Manipulable reputation:** star ratings can be faked, inflated by collusion, or used for revenge.
5. **Research gap:** [PCS] was evaluated only in MATLAB simulation.

### 1.2 The solution and the core loop

```
 Plan (CPM) ─► Hire a fair team (filter + PSO) ─► Monitor work (evidence) ─► Pay (escrow) ─► Review ─► Update reputation
                    ▲                                                                                   │
                    └──────────────────────────── next team is chosen more fairly ◄─────────────────────┘
```

### 1.3 What comes from the paper and what is ours

| From [PCS] (implement exactly, §9) | DevSync extensions (ours) |
|---|---|
| Reputation = competency (expertise & diversity, communication) + prior performance (project reviews, re-employment, timeliness); teamwork capacity | Real multi-role platform; evidence-based inputs for every parameter |
| EWMA and multi-step time-balancing updates (Eq. 2–9) | Newcomer starting values and the newcomer filtering rule |
| Worker filtering, Algorithm 1 | Fairness dial (guaranteed newcomer minimum) and cost of fairness |
| Binary PSO team formation, Algorithm 2, fitness Eq. 17 | Exact solver for verification; team comparison; "why this team"; "why not selected" |
| Payment policy with reward and penalty (Eq. 20–23) | CPM planning, forecasting and risk dashboard; task board; check-ins; files; discussion |
| Evaluation metrics: utility (Eq. 24), QoE (Eq. 25), completion ratio, average payment | Milestone escrow, contribution splits, auto-approval; disputes; review integrity and collusion detection; team repair; post-mortem; client ratings; skill challenges; GitHub evidence |

### 1.4 Feature list (all must be built; priorities in §17)

**Accounts & security:** registration (client or developer), phone OTP, email verification, login, sessions, password reset, admin TOTP 2FA with recovery codes, account settings, data export, account deletion.

**Profiles:** developer profile (bio, skills with levels, availability hours/week, GitHub username, portfolio items with screenshots, certificates with admin verification), client profile (organization, history), public profile pages, reputation dashboard.

**Skill challenges:** timed multiple-choice tests from a randomized question bank (core); auto-graded coding challenges in a sandbox (Judge0) (expected).

**Marketplace:** landing page; project search with filters (skill, budget, deadline, role, team size, availability); project details; recommended projects.

**Project planning:** multi-step creation wizard; milestones with durations, skills, payment shares; finish-to-start dependencies; cycle detection; CPM timeline (dependency graph + Gantt + table); baselines; plan change agreement; cancellation with refunds.

**Bidding:** sealed bids (developers never see others' bids); one bid per project; price + days needed + slot + proposal (+ optional portfolio items, expected contribution); edit/withdraw; Algorithm 1 filtering with newcomer rule; availability reservation (no double booking); too-few-bids handling.

**Team formation:** priority sliders (paper weights C1–C4) and presets mapped to Algorithm 1's advancement choice; fairness dial; BPSO; exact-solver verification (≤ 18 candidates); top candidate team comparison; "why this team" with team risks; "why not selected" with price counterfactual; saved, reproducible runs; invitations.

**Team:** 48-hour invitations; team-lead selection where the system recommends and the client makes the final choice (§1.6); lead change requests; team repair with project impact and ranked candidates; reopen bidding / raise budget.

**Workspace & monitoring:** client progress watching (§1.6); overview; Kanban task board (drag-and-drop) with assignee, deadline, estimate, difficulty, dependencies, files, comments, evidence; weekly check-ins; project files; per-project discussion threads; GitHub evidence; activity evidence events; monitoring dashboard (progress, schedule progress, budget usage, forecast, deadline impact, team health, risk level); risk dashboard (critical/medium/low with explanations); no surveillance.

**Deliverables & payments:** task evidence; milestone submission by the lead; approve with rating / request changes with reason / open dispute; auto-approval after 7 days; simulated wallets; milestone escrow + platform fee + bonus pool; contribution splits with evidence-based suggestion; [PCS] reward/penalty policy; earnings page; immutable double-entry ledger.

**Reviews & reputation:** blind reviews (client→developer, developer→developer, developer→client); contesting reviews; [PCS] reputation model with evidence inputs; reputation history with explanations; post-mortem.

**Integrity:** reviewer trust; robust aggregation; evidence consistency checks; peer outlier detection; collusion rules R1–R4; bidding anomaly rules B1–B3; self-dealing detection.

**Disputes:** open with category; automatic evidence; statements; admin decisions (full, partial, refund, revision, new split, remove review) with written reasons.

**Administration:** dashboard; users (search, suspend, restore, verify certificates); projects; disputes; integrity flags; platform alerts; team-formation runs with verification; fairness analytics; reputation tools (recalculate); payments overview; settings with version history; audit log viewer.

**Notifications:** in-app (bell + page) and email for key events; user preferences.

**Evaluation:** market simulator with attack injection; experiment runner (E1–E9).

### 1.5 Glossary

| Term | Meaning |
|---|---|
| Client | User who posts and pays for a project ([PCS] "buyer", $b_j$) |
| Developer | Freelance worker ([PCS] "worker", $w_i$) |
| Team lead | A developer who coordinates one project's team (per-project role) |
| Newcomer | Developer with fewer than `newcomer_threshold` (default 3) completed projects |
| Milestone | Planned unit of work with duration, dependencies, skills, payment share |
| Task | Unit of work inside a milestone, assigned to one member |
| Slot | A required skill position in the team (e.g. "React developer") |
| Bid | A developer's sealed offer for one slot: price $c_i$, days needed $t_i$ |
| Candidate set $S$ | Bids that pass Algorithm 1 filtering |
| Fitness | Team score from Eq. 17 |
| CPM | Critical Path Method: earliest/latest dates, slack, critical milestones |
| Evidence | System-recorded facts: dates, approvals, revisions, check-ins, reply times, test scores, commits |
| Escrow | Simulated money held for a milestone until approval or dispute resolution |
| Cost of fairness | Relative fitness lost by enforcing the newcomer minimum |
| Paisa | 1/100 BDT; all money is stored as integer paisa |

### 1.6 Key behaviours (clarified; implement exactly)

**Client progress watching.** The client of a project can watch its progress at any time after the project starts, without micromanaging the team. The client has read access to the whole project workspace and these client-facing views:
- **Overview / monitoring dashboard:** overall progress, schedule progress (planned vs actual), budget usage (released, committed, remaining), forecast finish date and deadline impact, team health, overall risk level, top risks, upcoming milestone, recent activity.
- **Timeline:** Gantt chart with baseline vs forecast and the critical path.
- **Risks:** the risk dashboard (critical, medium, low) with explanations and suggested actions.
- **Milestones and payments:** status of every milestone, submissions, revisions, escrow state, auto-approval countdowns.
- **Tasks board (read-only), check-ins feed, files, discussion, evidence:** the client sees the team's work and can comment and discuss, but cannot create, assign or move tasks.
- **Notifications:** CRITICAL risks, submissions waiting for review, auto-approval warnings and payment events are pushed to the client (in-app + email).

Division of monitoring responsibility: **the team lead manages the day-to-day work** (tasks, assignments, blockers), **the client oversees** milestones, deadline, risks and money, and **the system watches both automatically** (forecast and risk engine every 15 minutes and on events) and alerts whoever needs to act.

**Team lead selection: the system recommends, the client chooses.**
1. When every invited developer has accepted, the system **recommends** a lead: the accepted member with the highest teamwork capacity $X_m$; ties broken by more completed projects, then higher competency $C$, then earlier acceptance. The recommendation card shows the reason ("Highest teamwork capacity: 86; led 2 past teams").
2. The **client makes the final choice**: accept the recommendation or pick any other accepted member. The project cannot start until the client confirms a lead.
3. The chosen developer can **decline the lead role** (not the team); the system then recommends the next member by the same ranking and the client chooses again.
4. After the project starts, the **client can change the lead** at any time (reason recorded); **members can request a change** with a reason, and the client decides.
5. If the lead leaves the project, the system recommends a new lead from the remaining members by the same rule, and the client confirms (in parallel with team repair for the empty slot).
6. Lead status is per project (`team_members.is_lead`); it grants lead permissions only inside that project.

---

## 2. Roles and permissions

### 2.1 Roles

| Role | How obtained | Notes |
|---|---|---|
| Guest | Not logged in | Landing page, public project list (limited fields), public developer profiles (limited), sign-up, login |
| Client | Chosen at registration | Owns projects |
| Developer | Chosen at registration (UI label "Developer"; [PCS] "worker") | Bids and works |
| Team lead | Per project: `team_members.is_lead = true` | Not a sign-up role; a developer can lead one project and be a member of another |
| Admin | Created only by another admin via CLI (`make create-admin`) or admin UI | TOTP 2FA mandatory |

One account has exactly one primary role (`CLIENT`, `DEVELOPER`, `ADMIN`). A person who wants both client and developer roles needs two accounts, and the phone-uniqueness rule (§14.4) means two phone numbers; self-dealing detection (§9.15) watches for linked accounts.

### 2.2 Permission matrix (enforced in `app/core/authz.py`; deny by default)

| Action | Guest | Client | Developer | Team lead (own project) | Admin |
|---|---|---|---|---|---|
| View landing, public project cards | ✓ | ✓ | ✓ | ✓ | ✓ |
| View full project details | | own | open projects + member | ✓ | ✓ |
| Create/edit/publish/cancel project | | own (state rules §8) | | | cancel only (with reason) |
| View bids of a project | | own project | own bid only (sealed) | own bid only | ✓ |
| Place/edit/withdraw bid | | | ✓ (open projects) | ✓ | |
| Run team formation, view runs | | own project | | | ✓ (view, verify) |
| "Why not selected" | | | own bid | own bid | ✓ |
| Accept/decline invitation | | | own | own | |
| Recommend team lead (performed automatically by the system, §1.6) | | | | | |
| Choose/change team lead (final decision) | | own project | request change | request change / decline role | |
| Watch project progress: overview dashboard, timeline, risks, milestones, check-ins feed, read-only task board | | own project | member | ✓ | ✓ (read-only) |
| Create/assign tasks | | | | ✓ | |
| Move tasks | | | own tasks | all tasks | |
| Post check-in | | | member | ✓ | |
| Comment / discussion | | own project | member | ✓ | read (dispute context) |
| Upload project files | | own project | member | ✓ | read (dispute context) |
| Attach task evidence | | | own tasks | ✓ | |
| Submit milestone | | | | ✓ | |
| Approve / request changes | | own project | | | |
| Fund escrow | | own project | | | |
| Propose split | | | | ✓ | |
| Agree/object split | | | member | ✓ | |
| Review (blind) | | own completed project: each developer | own completed project: teammates + client | ✓ | |
| Contest review | | about self | about self | ✓ | decide |
| Open dispute | | own project | member | ✓ | |
| Resolve dispute | | | | | ✓ (not involving themselves) |
| Wallet / earnings | | own | own | own | read all (support) |
| Integrity flags, platform alerts | | | | | ✓ |
| Users (suspend/restore/verify cert) | | | | | ✓ |
| Settings | | | | | ✓ (step-up TOTP) |
| Audit log | | | | | ✓ (read-only) |
| Fairness analytics, experiments view | | | | | ✓ |
| Data export / delete own account | | ✓ | ✓ | ✓ | ✓ (not last admin) |

Every row has authorization tests: anonymous → 401, wrong role → 403, right role but wrong object → 404 (do not reveal existence), correct → 2xx (§16.4).

---

## 3. Technology stack

| Layer | Choice (pin exact versions in lock files) | Why |
|---|---|---|
| Frontend | React 18, TypeScript 5 (strict), Vite 5 | Fast, typed SPA |
| Routing | React Router 6 (data routers, lazy routes) | Code splitting per page |
| Server state | TanStack Query 5 | Caching, retries, optimistic updates |
| Forms & validation | React Hook Form + Zod (schemas mirror backend) | Typed client validation |
| UI components | Tailwind CSS 3 + shadcn/ui (Radix primitives, copied into repo) | Accessible primitives, full control |
| Icons | lucide-react | Consistent line icons |
| Motion | Framer Motion | Declarative, respects reduced motion; the only UI animation library |
| 3D (homepage hero only) | three (r160+, pinned), @react-three/fiber, @react-three/drei, optional @react-three/postprocessing | Lazy-loaded single scene (§13.12); never used on other pages |
| Charts | Recharts | Reputation trends, analytics, convergence |
| Gantt & dependency graph | Custom SVG components (no external lib) | Critical path styling, accessibility, zero CDN |
| Drag and drop | @dnd-kit/core + sortable | Accessible keyboard drag for Kanban |
| Code editor | CodeMirror 6 | Lightweight, no CDN |
| Fonts | Inter + JetBrains Mono via `@fontsource` (self-hosted) | No external requests (CSP) |
| Backend | Python 3.12, FastAPI, Pydantic v2, Uvicorn workers under Gunicorn | Typed, fast, OpenAPI |
| ORM & migrations | SQLAlchemy 2 (async, asyncpg) + Alembic | Mature, typed |
| Database | PostgreSQL 16 | Transactions, row locks, JSONB, constraints |
| Cache, rate limits, queues | Redis 7 | One dependency for three needs |
| Background jobs | RQ (Redis Queue) workers + a scheduler container using APScheduler that enqueues RQ jobs | Simple, inspectable |
| Algorithms | NumPy, NetworkX (collusion graphs) | Vector maths, graph cycles/SCCs |
| Passwords | argon2-cffi (Argon2id) | Memory-hard hashing |
| TOTP | pyotp | Admin 2FA |
| Password strength | zxcvbn (python) + bundled top-100k breached password list (offline) | No external calls |
| CAPTCHA | ALTCHA (self-hosted proof-of-work widget + `altcha` server library) | No third-party requests; CSP-compatible; works offline |
| Images | Pillow (re-encode uploads, strip metadata) | Upload safety |
| File type sniffing | python-magic | Content-type by signature |
| HTTP client | httpx with explicit timeouts | GitHub API, Judge0 |
| Code sandbox | Judge0 CE (self-hosted, isolated network) | Coding challenges |
| Reverse proxy / load balancer | Nginx | TLS, rate limits, timeouts, compression, static files, LB |
| Email | SMTP adapter; Mailpit in development | Test mailbox |
| Backend tests | pytest, pytest-asyncio, pytest-cov, hypothesis, factory-boy, httpx AsyncClient, testcontainers (Postgres/Redis), schemathesis | All layers |
| Frontend tests | Vitest, React Testing Library, MSW (mock service worker), @axe-core/react | Unit/component/a11y |
| End-to-end & visual | Playwright (+ @axe-core/playwright, screenshot comparisons) | Browser flows |
| Load tests | k6 | Thresholds in CI |
| Security tooling | Bandit, Semgrep, pip-audit, npm audit, gitleaks, Trivy, OWASP ZAP baseline, schemathesis fuzzing | §14, §16 |
| Lint/format/types | ruff (lint+format), mypy (strict for core), ESLint (typescript-eslint, react, jsx-a11y, security), Prettier, `tsc --noEmit` | Quality gates |
| Containers | Docker, Docker Compose (dev, test, prod profiles) | Reproducible |
| CI | GitHub Actions | Runs the phase gate |
| Observability | structlog (JSON logs), Prometheus metrics endpoint (internal only), request IDs | Debugging and load tests |

---

## 4. Repository layout

Create exactly this structure (add files as phases require; empty placeholders get a docstring/README line).

```
devsync/
├── CLAUDE.md
├── DEVSYNC_BUILD_SPEC.md
├── PROGRESS.md
├── DECISIONS.md
├── README.md
├── Makefile                      # all commands (§16.6)
├── .phase                        # current completed phase number
├── .env.example                  # every variable with safe dev defaults and comments
├── docker-compose.yml            # base services
├── docker-compose.dev.yml        # hot reload, mailpit, exposed ports for dev only
├── docker-compose.test.yml       # ephemeral db/redis for CI
├── docker-compose.prod.yml       # replicas, resource limits, read-only fs
├── .github/workflows/ci.yml
├── .pre-commit-config.yaml
├── infra/
│   ├── nginx/
│   │   ├── nginx.conf            # upstreams, LB, TLS, headers, limits, timeouts, gzip/brotli, caching
│   │   ├── security-headers.conf
│   │   └── certs/                # dev self-signed certs generated by `make certs` (gitignored)
│   ├── postgres/init/            # roles: devsync_migrator (DDL), devsync_app (DML only), devsync_readonly
│   ├── judge0/                   # judge0.conf (isolated network)
│   └── k6/                       # load test scripts
├── backend/
│   ├── pyproject.toml            # ruff, mypy, pytest, coverage, bandit config
│   ├── requirements.lock         # hashed (pip-compile --generate-hashes)
│   ├── requirements-dev.lock
│   ├── alembic.ini
│   ├── alembic/versions/
│   ├── app/
│   │   ├── main.py               # app factory, middleware order (§14.10), routers
│   │   ├── core/
│   │   │   ├── config.py         # pydantic-settings; validates insecure combos (§6.1)
│   │   │   ├── security.py       # hashing, tokens, constant-time compare
│   │   │   ├── sessions.py       # opaque server-side sessions in Redis + DB
│   │   │   ├── csrf.py
│   │   │   ├── authz.py          # central policy: can(user, action, resource)
│   │   │   ├── ratelimit.py      # Redis sliding window + token bucket
│   │   │   ├── errors.py         # error codes → HTTP mapping, safe messages
│   │   │   ├── logging.py        # structlog, redaction processor, request ids
│   │   │   ├── audit.py          # append-only audit writer
│   │   │   ├── idempotency.py
│   │   │   ├── cache.py          # cache-aside helpers, versioned keys, invalidation
│   │   │   ├── money.py          # paisa helpers, formatting, allocation without loss
│   │   │   ├── clock.py          # injectable clock (tests can freeze time)
│   │   │   └── redirects.py      # safe return_to validation
│   │   ├── db/                   # engine, session, base, mixins (timestamps, soft delete)
│   │   ├── models/               # SQLAlchemy models (§7)
│   │   ├── schemas/              # Pydantic request/response models (extra="forbid")
│   │   ├── repositories/         # query helpers (no business rules)
│   │   ├── services/             # business rules, state machines, transactions
│   │   ├── api/v1/               # routers per module
│   │   ├── algorithms/           # PURE: reputation.py, filtering.py, fitness.py, bpso.py,
│   │   │                         #   exact_solver.py, fairness.py, explain.py, repair.py,
│   │   │                         #   cpm.py, forecast.py, risks.py, payment_policy.py,
│   │   │                         #   splits.py, review_aggregation.py, trust.py,
│   │   │                         #   collusion.py, bid_anomaly.py, recommend.py, metrics.py
│   │   ├── jobs/                 # RQ job functions + scheduler definitions
│   │   ├── integrations/         # github.py, judge0.py, email.py, sms.py (+ fakes)
│   │   └── uploads/              # validation, re-encoding, storage, signed URLs
│   ├── scripts/                  # create_admin.py, seed_demo.py, simulate_market.py,
│   │                             #   run_experiments.py, check_forbidden.py, phase_gate.py
│   └── tests/
│       ├── conftest.py           # fixtures (§16.3)
│       ├── unit/  algorithms/  property/  integration/  api/  security/  jobs/  perf/
│       └── fixtures/             # generated at test time; no committed secrets
├── frontend/
│   ├── package.json  package-lock.json  vite.config.ts  tsconfig.json
│   ├── tailwind.config.ts        # design tokens (§13.1)
│   ├── index.html                # no inline scripts; CSP-compatible
│   ├── src/
│   │   ├── main.tsx  app/        # router, providers, layouts, route guards
│   │   ├── design/               # tokens.css, motion.ts, theme provider
│   │   ├── components/ui/        # shadcn primitives (button, input, dialog, …)
│   │   ├── components/           # shared composites (Gantt, DependencyGraph, KanbanBoard,
│   │   │                         #   ReputationRadar, StatCard, DataTable, EmptyState, …)
│   │   ├── features/             # auth, landing, marketplace, profile, challenges, projects,
│   │   │                         #   planner, bids, formation, team, workspace, monitoring,
│   │   │                         #   deliverables, payments, reviews, reputation, disputes,
│   │   │                         #   notifications, admin, settings
│   │   ├── api/                  # typed client generated from OpenAPI (openapi-typescript) + fetch wrapper
│   │   ├── lib/                  # format (money, dates), guards, csrf, errors
│   │   └── test/                 # MSW handlers, render helpers
│   └── tests/                    # vitest unit/component tests
├── e2e/                          # Playwright tests, page objects, fixtures, visual baselines
├── docs/                         # §21
└── runs/                         # gate reports, experiment outputs (gitignored except README)
```

---

## 5. Architecture

### 5.1 Runtime topology

```
                 Internet / LAN
                       │ 443 (80 → 301 to 443)
                ┌──────▼───────┐
                │    Nginx     │  TLS, HSTS, security headers, request limits, timeouts,
                │ (edge + LB)  │  gzip/brotli, static SPA (immutable hashed assets),
                └──┬────────┬──┘  per-IP rate limit (coarse), least_conn upstream
         /api/*    │        │  /*  (SPA files from frontend build)
        ┌──────────▼──┐  ┌──▼──────────────┐
        │ api (×N)    │  │ static files    │
        │ Gunicorn +  │  └─────────────────┘
        │ Uvicorn     │──────────┐
        └──┬──────┬───┘          │ enqueue
           │      │       ┌──────▼──────┐     ┌────────────┐
   asyncpg │      │ redis │  Redis      │◄────┤ scheduler  │ (APScheduler → RQ)
           │      └──────►│ cache,      │     └────────────┘
           │              │ sessions,   │     ┌────────────┐
           │              │ rate limits,│◄────┤ worker (×M)│ RQ: PSO, explanations,
   ┌───────▼──────┐       │ queues      │     │            │ reputation, integrity,
   │ PostgreSQL   │◄──────┴─────────────┘     │            │ GitHub sync, email, alerts
   │ (+ PgBouncer │◄──────────────────────────┤            │
   │  in prod)    │                           └─────┬──────┘
   └──────────────┘                                 │ internal network only
                                              ┌─────▼──────┐   ┌───────────┐
                                              │ Judge0 CE  │   │ SMTP /    │
                                              │ (isolated) │   │ Mailpit   │
                                              └────────────┘   └───────────┘
```

Networks (Compose): `edge` (nginx), `app` (nginx, api, worker, scheduler, redis, postgres), `sandbox` (worker ↔ judge0 only; judge0 has **no** route to `app` or the internet). Only Nginx publishes ports.

### 5.2 Backend layering (strict)

`api` (HTTP only: auth deps, schemas, status codes) → `services` (rules, transactions, authorization calls, state transitions, audit) → `repositories` (queries) → `models`. `algorithms` are called only from services and jobs. `integrations` are called only from jobs/services via interfaces with fake implementations for tests. Import rules are enforced by `scripts/check_layers.py` (AST scan) in the gate.

### 5.3 Key design decisions (copy into `docs/ARCHITECTURE.md`)

1. **Opaque server-side sessions, not JWT in the browser.** Session id in an `HttpOnly; Secure; SameSite=Lax` cookie; session data in Redis with a DB record for revocation/listing. Simple revocation, no token theft via XSS storage.
2. **CSRF double-submit token** for all state-changing requests (§14.6).
3. **Heavy work is asynchronous:** PSO runs, explanations, reputation updates, integrity scans, GitHub sync and emails run in RQ workers; the API returns `202` + job id; the UI polls `/jobs/{id}` (or SSE stream §10.3).
4. **Stateless API replicas** behind Nginx `least_conn`; all shared state in Postgres/Redis; safe to scale horizontally.
5. **Money uses a double-entry ledger** in Postgres with constraints that make the books always balance (§7, §9.12).
6. **Pure algorithms** for testability and paper alignment.
7. **Polling + SSE, no WebSockets:** less attack surface; SSE for job progress and notifications with cookie auth and Origin checks.
8. **Self-hosted everything** (fonts, icons, libraries): strict CSP with no third-party origins.

---

## 6. Configuration and platform settings

### 6.1 Environment variables (`backend/app/core/config.py`, documented in `.env.example`)

| Variable | Default (dev) | Notes |
|---|---|---|
| `DEVSYNC_ENV` | `development` | `development` \| `test` \| `production` |
| `SECRET_KEY` | (generated by `make env`) | ≥ 64 random bytes base64; startup fails if missing/short in production |
| `DATABASE_URL` | `postgresql+asyncpg://devsync_app:…@postgres:5432/devsync` | App role has DML only |
| `MIGRATION_DATABASE_URL` | `…devsync_migrator…` | Used only by Alembic |
| `REDIS_URL` | `redis://redis:6379/0` | Password required in production |
| `PUBLIC_ORIGIN` | `https://localhost` | Used for CORS, CSRF Origin checks, email links, redirects |
| `ALLOWED_HOSTS` | `localhost` | TrustedHost middleware |
| `SESSION_ROTATE_MINUTES` / `SESSION_IDLE_MINUTES` / `SESSION_ABSOLUTE_HOURS` | `15` / `30` / `168` | §14.4 (proposal NFR-SEC-1: 15-minute sessions, securely refreshed for up to 7 days) |
| `SMTP_HOST` … / `EMAIL_FROM` | Mailpit | |
| `SMS_PROVIDER` | `console` | `console` logs OTP **only in development**; startup fails if `console` in production |
| `GITHUB_TOKEN` | empty | Optional; read-only; stored only in env |
| `CAPTCHA_HMAC_KEY` | (generated by `make env`) | ALTCHA challenge signing (§14.16) |
| `ADMIN_ALLOWED_CIDRS` | empty | Optional Nginx allowlist for admin routes (§14.17) |
| `GITHUB_WEBHOOK_SECRET` | empty | Only if the optional webhook is enabled (§14.23) |
| `JUDGE0_URL` / `JUDGE0_AUTH_TOKEN` | `http://judge0:2358` | Internal network only |
| `UPLOAD_DIR` / `MAX_UPLOAD_MB` | `/data/uploads` / `20` | Outside web root |
| `TRUSTED_PROXY_IPS` | Nginx container IP range | For correct client IP behind proxy |
| `GUNICORN_WORKERS` / `GUNICORN_TIMEOUT` / `MAX_REQUESTS` | `2×CPU+1` / `30` / `1000` (+jitter 100) | Memory leak protection |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_STATEMENT_TIMEOUT_MS` | `10` / `5` / `5000` | Jobs use 30000 |
| `CACHE_TTL_SECONDS_DEFAULT` | `60` | §15.1 |
| `LOG_LEVEL` | `INFO` | |

**Startup validation** (full list in §14.18): in `production`, refuse to start if `SECRET_KEY` weak, `SMS_PROVIDER=console`, debug on, `PUBLIC_ORIGIN` not https, Redis without password, `ALLOWED_HOSTS` contains `*`, or cookies not `Secure`. Print each failure clearly.

### 6.2 Platform settings (DB table `platform_settings`, versioned, admin-editable; defaults below)

All algorithm parameters live here (never hard-coded). Each change writes a new version row and an audit entry; runs and reputation logs store the settings version they used.

| Key | Default | Source / meaning |
|---|---|---|
| `rep.alpha_comm` (α) | 0.7 | [PCS] Eq. 2; Table 2 sets α, κ, f = 0.7 |
| `rep.alpha_team` (α_m) | 0.7 | Eq. 3 |
| `rep.kappa_ext` (κ_e) / `rep.kappa_int` (κ_x) | 0.7 / 0.7 | Eq. 5–6 (must be > 0.5 per paper) |
| `rep.alpha_x` / `rep.alpha_e` | 0.3 / 0.3 | Eq. 7–8 (must be < 0.5 per paper: older projects weigh more) |
| `rep.w_internal` (w_y) / `rep.w_external` (w_x) | 0.8 / 0.2 | Eq. 9 (w_y > w_x by default); if no verified external reviews exist, β uses internal only |
| `rep.f_default` | 0.7 | Eq. 4 weight; clients may override per run |
| `rep.g` (g1,g2,g3) | (0.5, 0.25, 0.25) | Eq. 12 weights; clients may override per run |
| `rep.gamma0_base` | 0.40 | Initial communication Γ⁰ (§9.1.3) |
| `rep.gamma0_per_verification` | 0.05 | per verified item (phone, email, complete profile, certificate), max Γ⁰ 0.60 |
| `rep.neutral` | 0.5 | Neutral starting value |
| `rep.max_change_per_project` | 0.15 | Cap per parameter per project (our extension) |
| `newcomer.threshold` | 3 | Completed projects |
| `newcomer.pass_mark` | 0.60 | Skill test score to pass filtering |
| `filter.P0` / `filter.C0` | 0.45 / 0.40 | Algorithm 1 defaults; client may override |
| `filter.shortlist_factor` | 3 | Shortlist size K = max(3·N, 20) per §9.2 |
| `pso.particles` | 30 | |
| `pso.max_iter` | 200 | [PCS] Table 2 MAX-IT |
| `pso.z1` / `pso.z2` | 1.5 / 1.5 | Cognitive / social (paper names z1, z2) |
| `pso.inertia` | 1.0 | Eq. 14 has no inertia term (equivalent to 1.0); configurable |
| `pso.v_max` | 4.0 | Velocity clamp (standard BPSO; our safeguard) |
| `pso.bounds` (b_l, b_u) | (−1, 1) | Initial velocity range; positions binary |
| `pso.early_stop_iters` | 40 | Stop if gbest unchanged |
| `pso.timeout_seconds` | 10 | Return best feasible so far |
| `exact.max_candidates` | 18 | Exact solver limit |
| `fairness.default_min_newcomers` | 1 if eligible newcomers exist, else 0 | |
| `pay.platform_fee_bp` | 500 | 5% in basis points |
| `pay.bonus_pool_bp` | 1000 | 10% of budget optionally reserved for rewards |
| `pay.q_max` | 0.25 | [PCS] maximum allowable quality variance |
| `pay.theta1` / `pay.theta2` | 4.0 / 4.0 | Eq. 22–23 amplification factors |
| `pay.auto_approve_days` | 7 | Our extension |
| `invite.expiry_hours` | 48 | |
| `split.objection_hours` | 72 | |
| `review.window_days` / `review.contest_days` | 7 / 14 | |
| `trust.*` | see §9.14 | |
| `consistency.threshold` | 0.4 | Review vs evidence mismatch |
| `alerts.inactive_days` / `alerts.repair_days` / `alerts.stalled_days` | 7 / 10 / 5 | |
| `bidding.min_bids_factor` | 1.0 | Need ≥ team size eligible bids |
| `bidding.extend_days` | 3 | Auto-extension offered when too few bids |
| `ratelimit.*` | see §14.8 | |

---

## 7. Data model

PostgreSQL 16. Conventions: `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`, `created_at`/`updated_at timestamptz NOT NULL`, money columns `BIGINT` paisa with `CHECK (>= 0)` where applicable, enums as PostgreSQL enums, all foreign keys indexed, `ON DELETE RESTRICT` unless stated. Soft delete only where stated (`deleted_at`). Append-only tables get a trigger that raises on `UPDATE`/`DELETE` (marked **AO**). The app DB role has no DDL rights and no `UPDATE/DELETE` on AO tables.

### 7.1 Identity and access

| Table | Columns (beyond id/timestamps) | Constraints / notes |
|---|---|---|
| `users` | `email citext UNIQUE`, `phone_e164 text UNIQUE`, `password_hash text`, `role user_role`, `status user_status (PENDING, ACTIVE, SUSPENDED, DELETED)`, `display_name text (1–80)`, `email_verified_at`, `phone_verified_at`, `payment_verified_at`, `failed_login_count int`, `locked_until`, `last_login_at`, `deleted_at` | Email normalized lower-case; phone E.164; deletion anonymizes PII (§14.12) |
| `sessions` | `user_id`, `token_hash bytea UNIQUE`, `csrf_secret bytea`, `ip inet`, `user_agent text(≤256)`, `created_at`, `last_seen_at`, `expires_at`, `revoked_at`, `step_up_until` | Token stored hashed (SHA-256); Redis mirrors active sessions |
| `otp_codes` | `user_id`, `purpose (PHONE_VERIFY, LOGIN_STEP_UP)`, `code_hash`, `expires_at`, `attempts int`, `consumed_at` | 6 digits, 5-min expiry, 5 attempts |
| `email_tokens` | `user_id`, `purpose (VERIFY, RESET)`, `token_hash`, `expires_at`, `consumed_at` | 32-byte random; 24 h verify, 30 min reset |
| `totp_credentials` | `user_id UNIQUE`, `secret_encrypted bytea`, `confirmed_at`, `last_used_step bigint` | Encrypted with key derived from SECRET_KEY (AES-GCM); replay protection via `last_used_step` |
| `recovery_codes` | `user_id`, `code_hash`, `used_at` | 10 codes, Argon2id-hashed |
| `devices_seen` | `user_id`, `fingerprint_hash`, `first_seen`, `last_seen` | New-device login notification; also used by self-dealing detection |
| `audit_log` **AO** | `actor_id NULL`, `actor_role`, `action text`, `entity_type`, `entity_id`, `before jsonb`, `after jsonb`, `ip inet`, `request_id`, `at` | Hash-chained: `prev_hash`, `hash = sha256(prev_hash ‖ canonical_json(row))` |

### 7.2 Profiles, skills, challenges

| Table | Columns | Notes |
|---|---|---|
| `skills` | `name UNIQUE`, `domain (FRONTEND, BACKEND, DATABASE, MOBILE, DESIGN, TESTING, DEVOPS, DATA)`, `active` | Admin-managed; `domain` used for ω (Eq. 1) |
| `developer_profiles` | `user_id UNIQUE`, `headline(≤120)`, `bio(≤2000)`, `hours_per_week smallint (1–80)`, `github_username`, `timezone`, `visibility (PUBLIC, CLIENTS_ONLY)` | |
| `developer_skills` | `user_id`, `skill_id`, `self_level smallint 1–5` | UNIQUE(user, skill) |
| `portfolio_items` | `user_id`, `title`, `description`, `url`, `skill_ids uuid[]`, `position` | ≤ 20 per user |
| `portfolio_images` | `portfolio_item_id`, `file_id` | ≤ 5 per item |
| `certificates` | `user_id`, `title`, `issuer`, `file_id`, `status (PENDING, VERIFIED, REJECTED)`, `reviewed_by`, `reviewed_at`, `reason` | |
| `client_profiles` | `user_id UNIQUE`, `organization`, `description`, `website` | |
| `question_bank` | `skill_id`, `text`, `options jsonb (4)`, `correct_index`, `difficulty 1–3`, `active` | Correct answers never sent to client |
| `skill_tests` | `skill_id`, `title`, `question_count (10)`, `time_limit_seconds (600)`, `active` | |
| `test_attempts` | `test_id`, `user_id`, `question_ids uuid[]`, `answers jsonb`, `started_at`, `deadline_at`, `submitted_at`, `score numeric(4,3)`, `scored bool` | Server-side timer; one scored attempt / 30 days |
| `coding_challenges` | `skill_id`, `title`, `statement_md`, `language_id`, `starter_code`, `time_limit_ms`, `memory_limit_kb`, `active` | |
| `challenge_tests` | `challenge_id`, `stdin`, `expected_stdout`, `hidden bool` | |
| `coding_attempts` | `challenge_id`, `user_id`, `source_code(≤64 KB)`, `status`, `passed`, `total`, `score`, `scored bool`, `judged_at` | |
| `skill_evidence` | `user_id`, `skill_id`, `source (TEST, CODING, ADMIN_PORTFOLIO)`, `score`, `at` | Feeds newcomer ω and filtering |

### 7.3 Projects and planning

| Table | Columns | Notes |
|---|---|---|
| `projects` | `client_id`, `title(5–120)`, `summary(≤300)`, `description(≤10000)`, `requirements(≤5000)`, `budget_paisa`, `bonus_pool_paisa`, `deadline_days smallint (1–365)`, `start_date date`, `bidding_deadline timestamptz`, `team_size smallint 2–10`, `status project_status`, `cancel_reason`, `cancelled_at`, `completed_at`, `repo_url`, `settings_version`, `current_baseline_id` | |
| `project_slots` | `project_id`, `skill_id`, `label`, `count smallint ≥1` | Σ count = team_size |
| `milestones` | `project_id`, `name`, `description`, `duration_days smallint ≥1`, `share_bp int (0–10000)`, `position`, `status milestone_status`, `actual_start date`, `actual_finish date`, `revision_count smallint`, `submitted_at`, `approved_at`, `auto_approve_at` | Σ share_bp = 10000 (deferred check in service + DB trigger at publish) |
| `milestone_skills` | `milestone_id`, `skill_id` | |
| `milestone_dependencies` | `project_id`, `predecessor_id`, `successor_id` | UNIQUE pair; no self-loops (CHECK); acyclicity enforced in service |
| `plan_baselines` | `project_id`, `version`, `cpm jsonb`, `reason`, `created_by`, `approved_by_client`, `approved_by_lead` | Immutable once approved |
| `plan_change_requests` | `project_id`, `proposed_by`, `changes jsonb`, `status (PENDING, APPROVED, REJECTED)` | Needs client + lead approval after team confirmed |

### 7.4 Bidding, formation, team

| Table | Columns | Notes |
|---|---|---|
| `bids` | `project_id`, `developer_id`, `slot_id`, `price_paisa`, `days_needed smallint`, `proposal(≤3000)`, `expected_contribution(≤500)`, `portfolio_item_ids uuid[] (≤3)`, `status bid_status`, `ineligible_reasons jsonb` | UNIQUE(project, developer); sealed (§2.2) |
| `availability_reservations` | `developer_id`, `project_id`, `hours_per_week`, `from_date`, `to_date`, `status (TENTATIVE, CONFIRMED, RELEASED)` | §9.17 prevents double booking |
| `formation_runs` | `project_id`, `requested_by`, `status run_status`, `settings_version`, `params jsonb (weights C1–C4, f, g, P0, C0, advancement_choice, min_newcomers, seed)`, `candidate_snapshot jsonb`, `result jsonb (team, fitness, breakdown, top_teams, cost_of_fairness, convergence, risks, exact)`, `runtime_ms`, `error_code` | Reproducible: re-running with same snapshot+params+seed gives same result |
| `bid_explanations` | `bid_id`, `run_id`, `reasons jsonb`, `price_counterfactual_paisa`, `main_gap` | Visible only to bidder/admin |
| `teams` | `project_id UNIQUE`, `status`, `confirmed_at` | |
| `team_members` | `team_id`, `developer_id`, `bid_id`, `slot_id`, `price_paisa`, `days_needed`, `is_lead bool`, `status member_status`, `joined_at`, `left_at`, `left_reason` | Partial UNIQUE: one lead per team where status=ACTIVE |
| `invitations` | `team_member_id`, `expires_at`, `responded_at`, `response`, `is_replacement` | |
| `lead_change_requests` | `team_id`, `requested_by`, `reason`, `status` | |
| `repair_proposals` | `team_id`, `departed_member_id`, `impact jsonb`, `candidates jsonb`, `chosen_bid_id`, `status` | |

### 7.5 Workspace and monitoring

| Table | Columns | Notes |
|---|---|---|
| `tasks` | `milestone_id`, `title(≤160)`, `description(≤5000)`, `assignee_id`, `status task_status`, `deadline date`, `estimate_hours numeric(5,1)`, `difficulty (EASY, MEDIUM, HARD)`, `position`, `progress_pct smallint`, `last_activity_at` | |
| `task_dependencies` | `task_id`, `depends_on_task_id` | Same milestone only; acyclic |
| `task_evidence` | `task_id`, `kind (FILE, LINK, PR, SCREENSHOT)`, `file_id`, `url`, `note`, `added_by` | URLs validated (https only), never fetched |
| `comments` | `target_type (TASK, MILESTONE)`, `target_id`, `author_id`, `body(≤4000) plain text`, `mentions uuid[]`, `edited_at`, `deleted_at` | Edits kept in `comment_revisions` |
| `discussion_threads` / `discussion_posts` | per project: `title`; posts: `author_id`, `body(≤4000)`, `reply_to` | Basic project messaging (polling) |
| `checkins` | `team_member_id`, `week_start date`, `done`, `next`, `blockers`, `confidence 1–5`, `on_time bool` | UNIQUE(member, week) |
| `files` | `owner_id`, `project_id NULL`, `storage_key`, `original_name`, `mime`, `size_bytes`, `sha256`, `scan_status`, `deleted_at` | Stored outside web root; served via signed URL |
| `activity_events` **AO** | `project_id`, `actor_id`, `type`, `entity_type`, `entity_id`, `data jsonb`, `at` | Evidence catalogue §9.1.6 |
| `github_stats` | `project_id`, `developer_id`, `merged_prs`, `opened_prs`, `reviews_given`, `active_days`, `commits`, `synced_at` | |
| `risks` | `project_id`, `type`, `severity (CRITICAL, MEDIUM, LOW)`, `entity_type`, `entity_id`, `title`, `detail jsonb`, `status (OPEN, RESOLVED)`, `opened_at`, `resolved_at` | De-duplicated by (project, type, entity) |
| `forecast_snapshots` | `project_id`, `day`, `forecast jsonb`, `impact_days` | Daily; used by post-mortem |

### 7.6 Deliverables, money

| Table | Columns | Notes |
|---|---|---|
| `milestone_submissions` | `milestone_id`, `round`, `submitted_by`, `description`, `evidence_ids uuid[]`, `decision (PENDING, APPROVED, CHANGES, DISPUTED, AUTO_APPROVED)`, `rating smallint 1–5`, `reason`, `comment`, `decided_at` | |
| `accounts` | `owner_type (USER, PLATFORM, ESCROW, BONUS)`, `owner_id`, `project_id NULL`, `milestone_id NULL` | Ledger accounts |
| `ledger_transactions` **AO** | `kind (DEPOSIT, ESCROW_FUND, FEE, RELEASE, REWARD, PENALTY_REFUND, REFUND, DISPUTE_PARTIAL, BONUS_FUND, BONUS_RETURN)`, `reference_type`, `reference_id`, `idempotency_key UNIQUE`, `created_by`, `note` | |
| `ledger_entries` **AO** | `transaction_id`, `account_id`, `amount_paisa BIGINT` (signed) | DB constraint trigger: Σ amount per transaction = 0 |
| `account_balances` | `account_id UNIQUE`, `balance_paisa`, `version` | Updated in same transaction; CHECK(balance ≥ 0) for user & escrow accounts |
| `escrows` | `milestone_id UNIQUE`, `amount_paisa`, `status escrow_status`, `funded_at`, `frozen_reason` | |
| `contribution_splits` | `milestone_id UNIQUE`, `proposed_by`, `shares jsonb {member_id: bp}`, `status (PROPOSED, AGREED, DISPUTED, OVERRIDDEN)`, `agreements jsonb`, `deadline_at` | Σ bp = 10000 |
| `payouts` | `milestone_id`, `member_id`, `base_paisa`, `adjustment_paisa`, `policy jsonb (q_i, case, u, ε)`, `transaction_id` | |

### 7.7 Reviews, reputation, integrity

| Table | Columns | Notes |
|---|---|---|
| `reviews` | `project_id`, `reviewer_id`, `reviewee_id`, `kind (CLIENT_TO_DEV, DEV_TO_DEV, DEV_TO_CLIENT)`, `scores jsonb`, `overall smallint 1–5`, `comment(≤2000)`, `visibility (HIDDEN, VISIBLE)`, `weight numeric`, `flags jsonb`, `status (ACTIVE, CONTESTED, INVALIDATED)` | UNIQUE(project, reviewer, reviewee); immutable content (trigger blocks updates to scores/comment) |
| `milestone_ratings` | `submission_id UNIQUE`, `client_id`, `developer_ids uuid[]`, `rating`, `at` | Internal per-time-slot reviews for Eq. 6 |
| `external_reviews` | `developer_id`, `source`, `rating_norm`, `project_date`, `evidence_file_id`, `status (PENDING, VERIFIED, REJECTED)` | Admin-verified only; feeds Eq. 5 |
| `review_contests` | `review_id`, `reason`, `evidence_ids`, `status`, `decided_by`, `decision_reason` | |
| `reputation_snapshots` | `developer_id UNIQUE`, `omega`, `X`, `Xm`, `beta`, `mu`, `T`, `C`, `P`, `completed_projects`, `distinct_clients`, `settings_version`, `updated_at` | Current values |
| `reputation_skill` | `developer_id`, `skill_id`, `competency` | Per-skill view |
| `reputation_log` **AO** | `developer_id`, `project_id`, `parameter`, `old`, `new`, `inputs jsonb`, `formula_version`, `reason` | |
| `client_reputation` | `client_id UNIQUE`, `avg_rating`, `on_time_approval_rate`, `dispute_rate`, `completed_projects` | From DEV_TO_CLIENT reviews + behaviour |
| `reviewer_trust` | `user_id UNIQUE`, `value`, `components jsonb`, `computed_at` | |
| `integrity_flags` | `rule (R1, R2, R3, R4, CONSISTENCY, OUTLIER, B1, B2, B3, SELF_DEALING)`, `subject_type`, `subject_ids uuid[]`, `details jsonb`, `status (OPEN, CONFIRMED, DISMISSED)`, `decided_by`, `reason` | |
| `platform_alerts` | `type`, `severity`, `entity_type`, `entity_id`, `message`, `status` | |

### 7.8 Disputes, notifications, settings, jobs

| Table | Columns | Notes |
|---|---|---|
| `disputes` | `project_id`, `milestone_id NULL`, `review_id NULL`, `opened_by`, `category (MILESTONE_QUALITY, PAYMENT_SPLIT, UNFAIR_REVIEW, MEMBER_LEFT, OTHER)`, `claim(≤4000)`, `requested_outcome`, `status dispute_status`, `evidence_deadline`, `outcome jsonb`, `decided_by`, `decision_reason(≥20 chars)` | |
| `dispute_statements` | `dispute_id`, `author_id`, `body`, `file_ids` | |
| `dispute_evidence` | `dispute_id`, `kind`, `snapshot jsonb` | Auto-attached, frozen at opening time |
| `notifications` | `user_id`, `type`, `title`, `body`, `link_path`, `read_at` | `link_path` must be a relative app path |
| `notification_preferences` | `user_id`, `type`, `in_app bool`, `email bool` | |
| `email_outbox` | `to_email`, `template`, `payload jsonb`, `status`, `attempts`, `next_attempt_at` | Transactional outbox pattern |
| `platform_settings` | `version`, `values jsonb`, `changed_by`, `reason` | Latest = active |
| `jobs` | `type`, `status (QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED)`, `progress smallint`, `requested_by`, `result_ref`, `error_code`, `started_at`, `finished_at` | Mirrors RQ for authorization and UI |
| `idempotency_keys` | `user_id`, `key`, `request_hash`, `response jsonb`, `status_code`, `expires_at` | UNIQUE(user, key) |

### 7.9 Required indexes (in addition to FKs)

`projects(status, bidding_deadline)`, GIN on `projects` search vector (title, summary, skills), `bids(project_id, status)`, `bids(developer_id, status)`, `tasks(milestone_id, status, position)`, `activity_events(project_id, at)`, `notifications(user_id, read_at, created_at DESC)`, `reviews(reviewee_id, kind, status)`, `ledger_entries(account_id, transaction_id)`, `risks(project_id, status, severity)`, `audit_log(entity_type, entity_id, at)`, `sessions(user_id, revoked_at)`, partial index `team_members(team_id) WHERE is_lead AND status='ACTIVE'`.

---

## 8. State machines

Implement transitions only in services via a transition table (`allowed[(from, to)] → guard`). Invalid transitions raise `InvalidStateTransition` → HTTP 409 with code `INVALID_STATE`. Every transition writes an audit entry and, where listed, notifications.

**User:** `PENDING → ACTIVE` (phone + email verified) · `ACTIVE ↔ SUSPENDED` (admin, reason) · `ACTIVE → DELETED` (self-service deletion; irreversible anonymization).

**Project:**
```
DRAFT → BIDDING → FORMING → TEAM_PENDING → IN_PROGRESS → REVIEW_WINDOW → COMPLETED
  │        │         │            │              │
  └────────┴─────────┴────────────┴──► CANCELLED (rules below)
                                    IN_PROGRESS ↔ ON_HOLD (open blocking dispute)
BIDDING → BIDDING (deadline extended, max 2 times)
```
Guards: `DRAFT → BIDDING` requires valid plan (no cycles, shares = 100%, CPM duration ≤ deadline or client acknowledged warning), payment method verified, ≥ 1 slot, Σ slot counts = team size. `BIDDING → FORMING` when the client starts formation or the bidding deadline passes. `TEAM_PENDING → IN_PROGRESS` when all slots accepted and a lead chosen. `IN_PROGRESS → REVIEW_WINDOW` when every milestone is `PAID`. `REVIEW_WINDOW → COMPLETED` after reviews or 7 days.
**Cancellation:** before `IN_PROGRESS`: free; release reservations; refund nothing (no escrow yet). During `IN_PROGRESS`: allowed only if no milestone is `SUBMITTED`; funded escrows of un-started milestones are refunded to the client; active milestone escrow is frozen and an automatic dispute is opened for a partial payment decision; team members are notified; reputation is not penalized for members.

**Bid:** `ACTIVE → WITHDRAWN | INELIGIBLE (re-evaluated) | SELECTED | NOT_SELECTED`; `SELECTED → ACCEPTED | DECLINED | EXPIRED`.

**Team member:** `INVITED → ACTIVE → COMPLETED | LEFT | REMOVED` (removal needs admin approval after a dispute or 10-day inactivity with client request).

**Milestone:**
```
PLANNED → FUNDED → ACTIVE → SUBMITTED → APPROVED → PAID
                     ▲          │  └──► AUTO_APPROVED → PAID   (no client action within 7 days)
                     └──────────┘ CHANGES_REQUESTED (revision_count += 1)
any of ACTIVE/SUBMITTED → DISPUTED → (ACTIVE | APPROVED | PAID | REFUNDED) by admin decision
```
`FUNDED → ACTIVE` when all predecessors are `PAID` (or `APPROVED`) — first milestones activate at project start.

**Escrow:** `UNFUNDED → FUNDED → RELEASED | PARTIALLY_RELEASED | REFUNDED`; `FUNDED ↔ FROZEN`.

**Task:** `TODO ↔ IN_PROGRESS ↔ REVIEW ↔ DONE` (moves by assignee or lead; DONE only if dependencies DONE).

**Review:** `HIDDEN → VISIBLE` (both sides submitted or window closed) → `CONTESTED → ACTIVE | INVALIDATED`.

**Dispute:** `OPEN → EVIDENCE (72 h) → UNDER_REVIEW → RESOLVED`; `OPEN|EVIDENCE → WITHDRAWN`.

**Formation run:** `QUEUED → RUNNING → SUCCEEDED | INFEASIBLE | FAILED | TIMED_OUT (returns best feasible if any)`.

**Integrity flag:** `OPEN → CONFIRMED | DISMISSED`.

---

## 9. Algorithms (exact)

All functions in `backend/app/algorithms/` are pure, typed, deterministic (seeded `numpy.random.Generator`), and receive plain dataclasses. Every function's docstring names the equation it implements. `docs/PAPER_ALIGNMENT.md` maps every equation to its function and test.

### 9.0 Conventions and resolved ambiguities

Normalized ratings: a 1–5 star rating $r$ becomes $\hat r = (r-1)/4 \in [0,1]$. All reputation parameters are in $[0,1]$. When [PCS] is ambiguous, DevSync uses the default below, makes it a setting where possible, and lists it in §23 for the supervisor.

| # | Paper point | DevSync default |
|---|---|---|
| A1 | Timeliness: text says lower $T$ = higher reputation, but Eq. 11 gives faster workers higher $T$ | Implement Eq. 11 as written (higher = faster = better) |
| A2 | Eq. 11 assumes $t \le T^d$ | Clip each ratio to 1: late work contributes 0 |
| A3 | Eq. 17 "1 otherwise" for wrong team size | Infeasible solutions get $-\infty$ (never selected) |
| A4 | Initial communication: Γ⁰ from platform evaluation vs "set to zero" | Γ⁰ from verification (§9.1.3) |
| A5 | "ω + X = 1" after Eq. 4 | Interpreted as the weights $f$ and $1-f$ summing to 1 |
| A6 | Eq. 7–8 weight older projects more ($α_x, α_e < 0.5$) | Implemented as written (defaults 0.3) |
| A7 | $P$ used only in filtering, not in Eq. 17 | As written; `fitness.include_performance` setting (default false) adds $C_5·P_i$ if the supervisor wants it |
| A8 | External reviews source | Only admin-verified external reviews; if none, β uses internal reviews only |
| A9 | ω, μ undefined for fewer than 2 projects/hires | ω from skill evidence (§9.1.3); μ = 0.5 neutral |
| A10 | Eq. 18 normalizer $C$ undefined | $C$ = project budget after platform fee |
| A11 | Eq. 23 printed as $e^{(q_i-q_{max})θ_2}$, which exceeds 1 although ε ∈ [0,1] | $ε = e^{-(q_i-q_{max})θ_2}$ |
| A12 | Eq. 24 utility adds cost and quality deviation | Report Eq. 24 as written **and** the normalized variant $U' = φ(1-\bar c) + (1-φ)(1-q)$; label both |
| A13 | Eq. 14 has no inertia | Inertia setting defaults to 1.0 (equivalent), with velocity clamp $v_{max}$ |

**Paper replication vs DevSync extensions.** The defaults above are preserved, and the two are kept clearly apart:
- **Algorithm mode setting** (`algorithm.mode`): `devsync` (default, used by the product) and `pcs_replication`. Replication mode switches off every DevSync extension: newcomer rule and fairness dial, repair operator (infeasible solutions get only the A3 value, as in the paper), velocity clamp, change cap, evidence-based weighting and integrity checks of reviews, and skill-specific competency. It keeps only the unavoidable resolutions (A2, A3, A10, A11, A13), each of which is listed in the experiment output.
- **One named test per ambiguity** (`test_A1_timeliness_direction`, …, `test_A13_inertia`) demonstrates the chosen default with a hand-computed example, and, where a setting exists, shows the alternative interpretation too, so a change after the supervisor's answer is a one-line setting change with a failing/passing test to prove it.
- **Experiments report both modes where it matters** (E1, E2, E7, E8 run in both; E3–E6 are DevSync-only by nature). Every table and chart is labelled **"PCS replication"** or **"DevSync (with extensions)"**, and `docs/PAPER_ALIGNMENT.md` lists each equation as *exact*, *exact with documented resolution (A#)* or *DevSync extension*.

### 9.1 Reputation ([PCS] Section 4.1, Eq. 1–12)

#### 9.1.1 Inputs per completed project $n$ for developer $i$

Built by `services/reputation_inputs.py` from the database and passed to the pure functions:

| Input | Built from |
|---|---|
| `domain` $l$ | Domain of the developer's slot skill |
| `client_id` | Project client (for μ) |
| `t_ni`, `T_d` | $t$ = days from the member's first assigned milestone `actual_start` to their last assigned milestone `actual_finish`; $T^d$ = project `deadline_days` |
| `gamma_comm` $Γ^n$ | Communication rating for the project (§9.1.4) |
| `gamma_team` $Γ_m^n$ | Teamwork rating for the project (§9.1.5) |
| `internal_slots` | Normalized client milestone ratings in approval order (time slots $t$), followed by the normalized project-end client review, each already trust-weighted and integrity-filtered (§9.14) |
| `external_slots` | Normalized verified external review(s) for that period, if any |

#### 9.1.2 Equations (implement exactly)

```
Eq.1  ω_i = 1 − Σ_l n_i^l (n_i^l − 1) / (N_i (N_i − 1))                      (Simpson diversity over domains)
Eq.2  X_i^0 = Γ_i^0 ;  X_i^n = α · Γ_i^n + (1 − α) · X_i^(n−1)                 (communication)
Eq.3  X_m^0 = Γ_m^0 ;  X_m^n = α_m · Γ_m^n + (1 − α_m) · X_m^(n−1)            (teamwork capacity)
Eq.4  C_i = f · ω_i + (1 − f) · X_i
Eq.5  E_(1,i)^1 = E_i^1 ;  E_(1,i)^t = κ_e · E_i^t + (1 − κ_e) · E_(1,i)^(t−1)   (external, within a project, κ_e > 0.5)
Eq.6  I_(1,i)^1 = I_i^1 ;  I_(1,i)^t = κ_x · I_i^t + (1 − κ_x) · I_(1,i)^(t−1)   (internal, within a project, κ_x > 0.5)
Eq.7  λ_(1,i) = I_(1,i) ;  λ_(n,i) = α_x · I_(n,i) + (1 − α_x) · λ_(n−1,i)       (internal across projects, α_x < 0.5)
Eq.8  ε_(1,i) = E_(1,i) ;  ε_(n,i) = α_e · E_(n,i) + (1 − α_e) · ε_(n−1,i)       (external across projects, α_e < 0.5)
Eq.9  β_i = w_y · λ_(n,i) + w_x · ε_(n,i)          (w_y + w_x = 1; w_y > w_x by default)
Eq.10 μ_i = 1 − Σ_j φ_(i,j)^r (φ_(i,j)^r − 1) / (N_i^r (N_i^r − 1))            (re-employment diversity over clients)
Eq.11 T_i = 1 − (1/n) Σ_n min(t_(n,i) / T_j^d, 1)                               (A2 clip)
Eq.12 P_i = g1 · β_i + g2 · μ_i + g3 · T_i          (g1 + g2 + g3 = 1)
```

Rules: if no external reviews exist, $β_i = λ_{n,i}$ (A8). If no internal reviews exist, $β_i$ = `rep.newcomer_review` (default: platform mean β of developers with ≥ 3 projects, falling back to 0.6). Validate weight ranges on settings save (κ > 0.5, α_x/α_e < 0.5, sums = 1), rejecting invalid settings.

**Our extension, change cap:** after computing the new value of each parameter, clamp the change from the previous snapshot to ±`rep.max_change_per_project` (default 0.15) for $X$, $X_m$, $β$ (not for ω, μ, T, which are counts/ratios). Log both raw and capped values.

#### 9.1.3 Newcomer starting values (ours; A4, A9)

- $Γ^0$ = min(0.60, 0.40 + 0.05 × verified items), items ∈ {phone, email, complete profile, verified certificate}.
- $Γ_m^0$ = 0.5.
- ω for $N_i < 2$: $ω^0 = \min(0.5,\ 0.2 × D)$ where $D$ = number of distinct domains with skill evidence score ≥ `newcomer.pass_mark`. With exactly one completed project and no evidence, ω = 0.
- μ for $N^r < 2$: 0.5. $T$ with no projects: 0.5. β with no reviews: `rep.newcomer_review`.
- A developer is a newcomer while `completed_projects < newcomer.threshold`.

#### 9.1.4 Communication rating for one project, $Γ^n$ (ours: how the paper's abstract quality is measured)

```
E_comm = 0.5 · checkin_on_time_ratio            (on-time weekly check-ins / expected)
       + 0.3 · reply_score                      (median reply time to comments that mention them or ask them:
                                                 ≤ 24 h → 1, linear to 0 at 72 h; no such comments → 0.5)
       + 0.2 · claims_match                     (share of tasks they marked DONE that were not reopened,
                                                 and work started on or before the bid's promised date)
R_comm = normalized client "communication" category score from the CLIENT_TO_DEV review (trust-weighted)
Γ^n    = 0.6 · E_comm + 0.4 · R_comm            (if no client review: Γ^n = E_comm)
```

#### 9.1.5 Teamwork rating for one project, $Γ_m^n$ (ours)

```
peer     = trust-weighted mean of normalized DEV_TO_DEV overall scores (§9.14 rules)
help     = min(1, (blockers_answered + code_reviews_given_on_teammates_PRs) / 8)
Γ_m^n    = 0.8 · peer + 0.2 · help                (no peer reviews: 0.8 · 0.5 + 0.2 · help)
```

#### 9.1.6 Evidence events (`activity_events.type`)

`checkin.posted`, `checkin.missed`, `comment.posted`, `comment.replied`, `task.moved`, `task.done`, `task.reopened`, `task.evidence_added`, `milestone.submitted`, `milestone.approved`, `milestone.changes_requested`, `milestone.auto_approved`, `work.started` (first task move to IN_PROGRESS), `blocker.reported`, `blocker.answered`, `github.pr_merged`, `github.review_given`, `split.proposed`, `split.agreed`, `split.objected`, `member.left`, `member.replaced`. Each event has a JSON schema; the Phase 9 tests validate them.

#### 9.1.7 Outputs and per-skill competency

`ReputationSnapshot(omega, X, Xm, beta, mu, T, C, P, completed_projects, distinct_clients)`. Per-skill competency for display and filtering of a slot: $C_{i,s} = f·ω_{i,s} + (1-f)·X_i$ where $ω_{i,s}$ = ω computed over projects in skill $s$'s domain plus skill evidence (for newcomers). Filtering and fitness use $C_i$ (paper) by default; `fitness.use_skill_competency` (default false) switches to $C_{i,s}$ and is reported in DECISIONS.md if turned on.

### 9.2 Worker filtering — Algorithm 1 ([PCS] Section 4.2) + newcomer rule

Inputs: bids, reputation snapshots, project ($T^d$ = deadline days, $C''_j$ = budget after fee), thresholds $P_0$, $C_0$, advancement choice $a ∈ \{P, C, t, c\}$.

1. **Constraints (paper):** keep bid $i$ iff $P_i ≥ P_0$, $C_i ≥ C_0$, $t_i ≤ T^d$, $c_i ≤ C''_j$.
2. **Newcomer rule (ours):** for newcomers, replace the $P_0$ check by "skill evidence score for the slot's skill ≥ `newcomer.pass_mark`", and keep $C_i ≥ C_0$ only if `filter.newcomer_competency_check` (default false, since newcomer $C$ is built from starting values).
3. **Other gates (ours):** account active and not suspended; slot skill is in the developer's skills; availability reservation feasible (§9.17); no open confirmed integrity flag of type SELF_DEALING with this client.
4. **Relaxation (paper line 3–5 "reinitialize"):** (scale: $P_0$, $C_0$ and all reputation scores are stored and tested on 0–1; the UI shows them ×100 as whole numbers, so 0.45 → 0.40 is displayed as "45 → 40") if fewer eligible bids than `team_size` or any slot has fewer eligible bids than its count, relax $P_0$ and $C_0$ by 0.05 per step for up to 3 steps (never below 0). Report each relaxation step to the client ("Minimum performance relaxed from 45 to 40 to find enough candidates"). If still insufficient → `TOO_FEW_BIDS` (§9.19).
5. **Advancement choice (paper line 6):** order each slot's eligible bids — descending by $P$ (a = P) or $C$ (a = C); ascending by $t$ (a = t) or $c$ (a = c). Presets map: Quality → P, Balanced → C, Fast → t, Budget → c. Keep the top $K_s = \max(3 · count_s, 6)$ per slot as the shortlist $S$ passed to PSO (bounds search size; complexity O(M log M)).
6. Output: `FilterResult(eligible, shortlisted, rejected_with_reasons, relaxations)`. Reasons are stable codes with human text: `LOW_PERFORMANCE`, `LOW_COMPETENCY`, `TOO_SLOW`, `OVER_BUDGET`, `NO_SKILL_EVIDENCE`, `SKILL_MISMATCH`, `UNAVAILABLE`, `SUSPENDED`, `SELF_DEALING`, `NOT_SHORTLISTED`.

### 9.3 Fitness (Eq. 17–19) and binary PSO (Algorithm 2, Eq. 13–16)

**Normalization:** $\bar t_i = t_i / T^d_j$ (Eq. 19); $\bar c_i = c_i / C$ with $C$ = budget after fee (Eq. 18, A10).

**Fitness of a solution $X^p$** (Eq. 17, A3):
```
F(X^p) = Σ_{x_i = 1} ( C1·C_i + C2·X_(M,i) − C3·t̄_i − C4·c̄_i )   if the solution is feasible
       = −∞                                                         otherwise
C1 + C2 + C3 + C4 = 1 (client sliders, normalized); optional C5·P_i (A7)
```
**Feasible** (Eq. 13 + ours): Σ x_i = N, each slot gets exactly its count, distinct developers, Σ $c_i$ ≤ $C$, every required skill covered, newcomers ≥ `min_newcomers`. Store a per-member breakdown `{comp, team, time, cost}` for explanations.

**BPSO (Algorithm 2):**
```
for each particle p:  x^p ~ U{0,1} with P(1) = N/k ;  v^p ~ U(b_l, b_u)            (lines 3–6)
repeat until MAX_IT or early stop or timeout:
  for each particle p, dimension i:
     v_i ← ω·v_i + z1·r1·(L_i^p − x_i) + z2·r2·(gbest_i − x_i)    (Eq. 14; ω = inertia, default 1.0)
     v_i ← clamp(v_i, −v_max, v_max)
     x_i ← 1 if sigmoid(v_i) ≥ rand() else 0                     (Eq. 15–16)
  x^p ← repair(x^p)                                              (ours, below)
  if F(x^p) > F(L^p): L^p ← x^p ; if F(L^p) > F(gbest): gbest ← L^p   (lines 12–17)
T ← { s_i : gbest_i = 1 }                                        (lines 21–25)
```
**Repair operator (ours; keeps particles feasible so the swarm explores useful space):** in order — (1) per slot, drop lowest-marginal-score extras / add highest-marginal-score missing members (marginal score = member term of Eq. 17); (2) enforce newcomer minimum by swapping the weakest non-newcomer for the best newcomer in the same slot; (3) while over budget, swap the member with the worst score-per-paisa for the best cheaper alternative in the same slot; (4) ensure skill coverage; (5) if still infeasible, mark infeasible. Locked indices (team repair, forced inclusion) are never removed.
**Outputs:** team, fitness, breakdown, convergence history (gbest per iteration), evaluations, iterations, seed, `timed_out` flag, archive of the best distinct feasible teams seen (for comparison when the exact solver is not used).
**Complexity:** O(I · P · |X|) per [PCS] Section 4.5; must handle |S| = 200, N = 10, P = 30, I = 200 in < 5 s on the API host (perf test §16).

### 9.4 Exact solver (ours, verification)

Enumerate all feasible teams as the Cartesian product over slots of combinations (C(n_s, k_s)) when Σ n_s ≤ `exact.max_candidates` (18) and the product ≤ 2,000,000; evaluate Eq. 17; return best, top-3 distinct teams, count. Used for: verifying every run when small (store optimality gap), the admin "verify run" tool, forced-inclusion queries in §9.8, and experiment E1.

### 9.5 Fairness dial and cost of fairness (ours)

Run the optimizer twice with the same seed and shortlist: `min_newcomers = 0` → $F_0$, team $T_0$; `min_newcomers = k` → $F_k$, team $T_k$. Cost of fairness = $(F_0 - F_k)/|F_0|$ (0 if $F_0 ≤ 0$ or the constraint was not binding). Also report price difference $Σc(T_k) - Σc(T_0)$ and the newcomers included. If no feasible team satisfies $k$, return the maximum feasible $k$ and say so.

### 9.6 Team comparison (ours)

Top candidate teams = exact solver top-3 when available; otherwise the PSO archive (best distinct feasible teams by fitness). For each: fitness, total price, newcomers included, skill coverage (all required skills covered + extra skills), average competency, average teamwork, max days needed (expected completion = max $t_i$ over members, or CPM forecast with their days), and the difference from the recommended team.

### 9.7 "Why this team?" and team risks (ours)

Explanation payload: skill coverage per slot; budget used vs limit; expected completion vs deadline; newcomers included and the cost of fairness; each member's contribution to fitness by term; comparison with the runner-up (which terms made the difference); relaxations applied; verification status (optimal / gap %).
**Team risks** (shown as chips with severity): `SINGLE_POINT_SKILL` (a skill needed by a critical milestone is covered by exactly one member) · `BUDGET_TIGHT` (Σ price > 95% of $C$) · `SCHEDULE_TIGHT` (max $t_i$ > 90% of $T^d$) · `LOW_TEAMWORK` (team mean $X_m$ < 0.5) · `NEWCOMER_ON_CRITICAL_PATH` (informational).

### 9.8 "Why not selected" (ours)

For each eligible, non-selected bid (cap 50 per run; the rest get rule reasons): (1) filter reasons if rejected or not shortlisted; (2) forced-inclusion best team (exact solver with the bid locked, or PSO with the index locked) → gap Δ = $F^* - F_b$; (3) price counterfactual: binary search the factor $φ ∈ [0.5, 1]$ (10 iterations) for the highest price at which the forced team's fitness ≥ $F^*$, rounded down to ৳100; (4) main gap: compare with the selected member in the same slot and report the term with the largest weighted gap with a concrete, actionable hint (competency → "complete projects in more domains or pass skill tests"; teamwork → "teammates' ratings and helping with blockers raise this"; time → "selected bid needs X days, yours Y"; cost → "selected bid ৳A, yours ৳B"). Property test: the reported counterfactual price, when applied, actually yields selection.

### 9.9 Team repair (ours)

Triggered by decline, invitation expiry, leaving, removal, or inactivity ≥ `alerts.repair_days` (suggestion only). Lock remaining active members; candidates = eligible bids for the open slot that weren't declined and pass availability now. For each candidate (top 10 by marginal score), compute the best feasible team with that candidate forced in; rank by fitness; return top 3 with: skills, price, days, fitness, and **project impact** (forecast finish with the candidate's days applied to the departed member's unfinished milestones; affected milestones list; budget delta). The newcomer minimum is preserved only if a newcomer candidate exists for the slot (otherwise relaxed with an explicit note). If none: reasons (`NO_BIDS_FOR_SLOT`, `REMAINING_BUDGET_TOO_LOW` with shortfall, `NONE_AVAILABLE`) and actions: reopen bidding for the slot (48 h) or raise budget by the shortfall.

### 9.10 CPM and forecasting (ours)

Exactly as follows (milestone level; finish-to-start):
1. Validate: Kahn topological sort; if incomplete, find a cycle with DFS and return its milestone names in order.
2. Forward pass: ES = max(EF of predecessors, 0); EF = ES + duration.
3. Backward pass: LF = min(LS of successors) or project duration D; LS = LF − duration; slack = LS − ES; critical ⇔ slack = 0. Report all critical paths.
4. Dates: project start date + day offsets (calendar days).
5. Forecast at day `today` (project day index): DONE → actual finish; ACTIVE with progress $p ∈ (0,1)$ and elapsed $e$ → remaining = max(dur·(1−p), e·(1−p)/p), forecast finish = today + ceil(remaining); ACTIVE with $p = 0$ → max(planned EF, today + dur); not started → ES = max(forecast EF of predecessors, today if planned ES passed) and EF = ES + dur. Forecast project finish = max forecast EF; deadline impact = forecast finish − baseline D.
6. Must handle 300 milestones in < 50 ms.
Milestone progress $p$ = Σ(estimate × status weight)/Σ estimate with weights TODO 0, IN_PROGRESS 0.5, REVIEW 0.85, DONE 1.

### 9.11 Risk engine and monitoring metrics (ours)

| Risk type | Rule | Severity |
|---|---|---|
| `CRITICAL_PATH_DELAY` | critical milestone forecast EF > baseline EF | CRITICAL |
| `SLACK_EATEN` | non-critical milestone used > 50% of its slack | MEDIUM |
| `DEADLINE_IMPACT` | project impact ≥ 1 day (updates value) | CRITICAL if impact > 10% of D else MEDIUM |
| `SKILL_DEPENDENCY` | a not-done critical milestone needs a skill held by exactly one active member who is inactive ≥ 5 days or overloaded | MEDIUM |
| `CAPACITY` | member's open task estimate hours > hours_per_week × weeks until those tasks' deadlines | MEDIUM |
| `BUDGET` | (released + funded) / budget > progress + 20 points | MEDIUM; client wallet < next milestone amount → LOW |
| `STALLED_TASK` | task IN_PROGRESS with no activity for 5 days (10 → MEDIUM) | LOW / MEDIUM |
| `INACTIVE_MEMBER` | no check-in and no task activity for 7 days (10 → CRITICAL + repair suggestion) | MEDIUM / CRITICAL |
| `AUTO_APPROVAL_SOON` | submitted milestone will auto-approve within 2 days (client only) | LOW |

Risks are upserted by (project, type, entity) and resolved automatically when the rule stops firing. **Team health:** Healthy (no CRITICAL, ≤ 1 MEDIUM), At risk (≥ 2 MEDIUM or 1 CRITICAL), Critical (≥ 2 CRITICAL). **Overall risk level** = highest open severity. **Schedule progress** = Σ share × progress vs Σ share of milestones planned to be done by today (earned schedule). **Budget usage** = released / budget and committed (funded, not released) / budget.

### 9.12 Payment policy (Eq. 20–23) and ledger postings

For each member $i$ of an approved milestone $m$:
```
base c_i^m     = floor(A × split_bp_i / 10000)                            (integer paisa, remainder to lead)
Π_i = 1 (assigned quality);  Π̂_i = 0.7·r̂ + 0.3·max(0, 1 − 0.25·revisions)   (actual quality; r̂ = normalized approval rating)
q_i = Π_i − Π̂_i                                                         (Eq. 20)
on_time        = milestone.actual_finish ≤ baseline EF
Eq.21 payment  = c + u      if q_i ≤ q_max and on_time
               = ε · c      if q_i > q_max
               = c          otherwise
Eq.22 u        = (V_i − c_i)·(1 − e^{(q_i − q_max)·θ1})   (≥ 0 because q_i ≤ q_max); u = 0 if V_i ≤ c_i
Eq.23 ε        = e^{−(q_i − q_max)·θ2}                    (A11; ε ∈ (0,1])
V_i            = median eligible bid price for the member's slot at formation × milestone share
```
Rewards are paid from the project's bonus pool (if the client enabled it); if the pool is insufficient, rewards are scaled down proportionally and the UI says so. Penalty differences ($c − εc$) are refunded to the client. Auto-approved milestones use $r̂ = 0.75$ (4 stars). Every payout stores `{q_i, case, u, ε, V_i}`.

**Ledger postings** (each a balanced transaction with an `idempotency_key`; full rules and worked examples in §9.12.1): `ESCROW_FUND` (client −G, platform +F, escrow +A, where A = G − F); `RELEASE` (escrow −A, members +payouts, client +any penalty refund); `REWARD` (bonus −u, member +u); `DISPUTE_PARTIAL`; `BONUS_FUND` / `BONUS_RETURN`; `REFUND`. All within one DB transaction with `SELECT … FOR UPDATE` on the escrow and the affected balances.

#### 9.12.1 Worked ledger examples (implement as tests; every number must reconcile)

**Funding rule:** the client pays the milestone's gross amount $G$ (= budget × share). The platform fee $F$ = 5% of $G$ goes to the platform, and the rest $A = G − F$ is held in escrow for the team (so team formation's budget "after fee" matches). The bonus pool, if enabled, is funded once at project start. Every transaction below is **one** balanced posting (entries sum to zero); amounts are paisa.

Running example: milestone M2 of a ৳120,000 project, share 20% → $G$ = 2,400,000; $F$ = 120,000; $A$ = 2,280,000. Two members with an agreed split of 60/40: base $c_1$ = 1,368,000 and $c_2$ = 912,000. Bonus pool ৳12,000 (1,200,000).

**How to read the table (fixtures):** rows 0 and 1 are the **setup** (bonus pool funded, escrow funded). Rows 2, 3, 4 and 5 are **alternative, mutually exclusive outcomes** for the same milestone: each one starts from a **fresh fixture** containing only rows 0–1, never from another outcome. Row 6 (retry) builds on row 2 and repeats its request. Row 7 (bonus return) builds on row 3. Tests are written exactly this way: `test_payout_normal`, `test_payout_reward`, `test_payout_penalty` and `test_dispute_partial` each get a fresh fixture; `test_release_retry_is_idempotent` uses the state after row 2; `test_bonus_return_after_reward` uses the state after row 3.

| # | Case | Transaction (`kind`, idempotency key) | Entries (account: amount) | Check |
|---|---|---|---|---|
| 0 | Bonus pool funded at project start | `BONUS_FUND`, `bonus-fund:{project}` | client −1,200,000 · bonus +1,200,000 | Σ = 0 |
| 1 | Escrow funded | `ESCROW_FUND`, `fund:{milestone}` | client −2,400,000 · platform +120,000 · escrow(M2) +2,280,000 | Σ = 0 |
| 2 | **Normal payout** (q ≤ q_max but finished late → claimed price, Eq. 21 third case) | `RELEASE`, `release:{milestone}:r{round}` | escrow(M2) −2,280,000 · member1 +1,368,000 · member2 +912,000 | Σ = 0; escrow(M2) = 0 |
| 3 | **Reward** (rating 5, 0 revisions → Π̂ = 1, q = 0, on time). Member 1: claimed cost $c$ = bid ৳36,000 × 0.2 = 720,000; market value $V$ = median bid ৳42,000 × 0.2 = 840,000; $u = (V − c)(1 − e^{(0 − 0.25)·4})$ = 120,000 × 0.6321205588… → **75,854** (`ROUND_FLOOR`). Member 2's bid was above the median ($V ≤ c$) → $u$ = 0 | `RELEASE` as #2, then `REWARD`, `reward:{milestone}:{member1}` | (#2 entries) then bonus −75,854 · member1 +75,854 | Σ = 0 each; bonus = 1,124,146 |
| 4 | **Penalized payout** (rating 3 → r̂ = 0.5; 1 revision → Π̂ = 0.7·0.5 + 0.3·0.75 = 0.575; q = 0.425 > 0.25; ε = $e^{−(0.425−0.25)·4}$ = 0.4965853037…). Payments floor(ε·c) with `ROUND_FLOOR`: member1 **679,328**, member2 **452,885**; the rest returns to the client | `RELEASE`, `release:{milestone}:r{round}` | escrow(M2) −2,280,000 · member1 +679,328 · member2 +452,885 · client +1,147,787 | Σ = 0; refund = A − Σ paid; the fee is not refunded |
| 5 | **Partial dispute refund** (admin decides 60% release, 40% refund; the payment policy does not apply to admin decisions) | `DISPUTE_PARTIAL`, `dispute:{dispute_id}` | escrow(M2) −2,280,000 · member1 +820,800 · member2 +547,200 · client +912,000 | Σ = 0; release = floor(A × 0.6) split 60/40 |
| 6 | **Retry** of row 2 (the client double-clicks Approve, or the job crashes after posting and runs again) | Same idempotency key as row 2 | **No new entries.** The unique constraint on `idempotency_key` rejects the duplicate insert; the service returns the original transaction and the same API response | Balances unchanged; one release row |
| 7 | Bonus returned at project completion (after row 3) | `BONUS_RETURN`, `bonus-return:{project}` | bonus −1,124,146 · client +1,124,146 (after example 3) | Σ = 0; bonus = 0 |

**Arithmetic and rounding rules (exact, reproducible):**
- Stored amounts are integers (paisa). Everything fractional is computed with `Decimal` in the fixed context of `core/money.py` (precision 28); the exponentials in Eq. 22–23 use `Decimal.exp()`, never `math.exp` or floats.
- Conversion to paisa happens once per amount with `ROUND_FLOOR`: base splits (remainder to the team lead), rewards $u$, penalized payments $εc$ (remainder of the escrow refunded to the client), the platform fee, and partial dispute releases. No paisa is ever created or lost.
- Inputs to the policy are exact decimals: normalized ratings $\hat r = (r−1)/4$, the revision term, $q_{max}$, $θ_1$, $θ_2$ (settings stored as decimal strings, e.g. `"0.25"`, `"4"`).
- The values in the table were recomputed independently with `Decimal` and match exactly; they are mandatory test values.

**Reconciliation invariants** (checked by property tests in Phase 10 and nightly by `ledger.verify`; any failure raises a CRITICAL platform alert):
1. Every transaction's entries sum to exactly 0 (deferred constraint trigger).
2. Every account balance equals the sum of its entries.
3. Per milestone: $G$ = fee + Σ member payouts + client refunds + escrow remaining.
4. Per project bonus pool: funded = Σ rewards + returned + remaining.
5. Platform-wide: the sum of **all** account balances is 0. Simulated deposits come from an `EXTERNAL` account whose balance is negative, so money is never created from nothing.
6. User and escrow balances are never negative.

### 9.13 Contribution split suggestion (ours)

Suggested bp for member $i$: 0.7 × (completed task estimate hours of $i$ in $m$ / total) + 0.3 × (merged PRs of $i$ in milestone period / total) when GitHub is linked; otherwise task share only. Convert to basis points, largest-remainder rounding, sum exactly 10000. If no split is agreed when the milestone is approved, the suggestion is applied and recorded as `DEFAULT_APPLIED`.

### 9.14 Review aggregation and reviewer trust (ours)

```
trust(u) = clamp(0.1, 1, 0.25·min(1, age_days/90) + 0.25·min(1, completed/5) + 0.15·verified + 0.35·consistency_history)
           × 0 if confirmed colluder  × 0.5 if open flag
```
Rules applied before reviews enter Eq. 2/3/6: (1) only participants of the project can review (enforced at write); (2) one client counts as one voice per developer across projects in 12 months (collapse to the mean); (3) consistency check: compare client's normalized timeliness/quality category scores with measured evidence (T for the project; Π̂); if |diff| > `consistency.threshold` → weight × 0.5, mark `INCONSISTENT`, and if > 0.6 with an extreme rating raise flag CONSISTENCY; (4) peer outlier: a peer score > 0.4 from the team median for that reviewee, with no comment → weight × 0.5 + flag OUTLIER; (5) trimmed weighted mean when ≥ 5 values (drop top and bottom 10%, at least one each); (6) flagged or contested reviews weigh 0 until decided; (7) Bayesian smoothing for display scores only: $(m·μ + Σw r)/(m + Σw)$ with m = 3.

### 9.15 Integrity rules (ours)

| Rule | Detects | Condition |
|---|---|---|
| R1 Repeat pair | Client–developer mutual boosting | ≥ 3 completed projects together in 60 days, all client ratings ≥ 4.5/5, and developer has ≤ 1 other client |
| R2 Reciprocal inflation | Team rating each other perfectly | All peer scores maximum while Π̂ < 0.6 or ≥ 1 milestone late |
| R3 Rating ring | Circles of accounts | Strongly connected component (3–8 accounts) in the high-rating graph where ≥ 80% of each member's given ratings stay inside, mean ≥ 4.5 |
| R4 New-account burst | Throwaway accounts | Accounts < 14 days old giving or receiving ≥ 3 reviews |
| B1 Coordinated bids | Shill bidding | ≥ 3 accounts sharing a device fingerprint or /24 subnet bidding on the same project within 10 minutes |
| B2 Bid churn | Probing sealed bids | > 3 withdraw/re-bid cycles on one project |
| B3 Captive bidding | Fake competition | Accounts that bid only on a single client's projects (≥ 5 bids) |
| SELF_DEALING | Same person on both sides | Client and developer share device fingerprint, verified phone prefix pattern, or payment method fingerprint |

Rules run nightly and on relevant events; open flags reduce weights as in §9.14 and appear in the admin queue with an explanation and the effect on reputation (before/after).

### 9.16 Recommended projects (ours)

Open projects needing at least one of the developer's skills, whose deadline ≥ the developer's typical days for that skill (median of their past bids, else any), and whose required hours fit their availability; ordered by skill match count, then newest. Exclude projects already bid on. Cached 5 minutes per user.

### 9.17 Availability reservation (ours; prevents double booking)

Each bid declares `hours_per_week_committed` (default min(20, profile hours)). Invitation creates a TENTATIVE reservation; acceptance CONFIRMS; completion, decline, expiry or leaving RELEASES. A bid is `UNAVAILABLE` if Σ confirmed reservations overlapping the project period + this commitment > profile `hours_per_week`.

### 9.18 Evaluation metrics ([PCS] Section 5.2 + ours)

QoE (Eq. 25) = $1 - t_i / T^d_j$ (per member and team mean). Utility (Eq. 24) as written and $U'$ (A12). Task completion ratio. Average worker payment. Unreliable-worker detection rate (simulation with known unreliable workers). Gini coefficient of selection counts. Newcomer share of team places. Cost of fairness. Optimality gap vs exact. Runtime and iterations. Attack resistance (reputation gain with defences on vs off). Spearman correlation between reputation and latent true ability (simulation).

### 9.19 Too few bids (ours)

At the bidding deadline (or when the client starts formation) if eligible bids < team size or a slot is short after relaxation: notify the client with the shortfall per slot and offer: extend bidding by `bidding.extend_days` (max 2 times), lower minimum standards, raise the budget, reduce team size (re-plan slots), or cancel the project (free).

---

## 10. API specification

### 10.1 Conventions

- Base path `/api/v1`; JSON only (`Content-Type: application/json` required on bodies, else 415); UTF-8; OpenAPI at `/api/v1/openapi.json` (served only to admins in production; public in development); Swagger UI only in development.
- **Authentication:** session cookie `__Host-ds_session` (HttpOnly, Secure, SameSite=Lax, Path=/). **CSRF:** header `X-CSRF-Token` equal to the token from `GET /auth/csrf` (also set as readable cookie `__Host-ds_csrf`), required on POST/PUT/PATCH/DELETE (§14.6).
- **Errors:** `{"error": {"code": "BID_DEADLINE_PASSED", "message": "Bidding for this project closed on 12 Oct.", "fields": {"price_paisa": "Must be at least ৳500"}, "request_id": "…"}}`. Never include stack traces, SQL, internal ids of other users, or whether an account exists.
- **Status codes:** 200/201/202/204; 400 bad request; 401 unauthenticated; 403 forbidden (role); 404 not found or not yours; 409 invalid state / conflict / version mismatch; 413 payload too large; 415; 422 validation; 423 locked account; 429 rate limited (`Retry-After`); 503 dependency unavailable (with safe message).
- **Pagination:** cursor-based `?cursor=&limit=` (limit ≤ 100, default 20) → `{items, next_cursor}`; admin tables may use page/size ≤ 100.
- **Filtering/sorting:** whitelisted fields only; unknown params → 400.
- **Optimistic concurrency:** mutable resources return `version`; updates send `If-Match: <version>`; mismatch → 409 `VERSION_CONFLICT`.
- **Idempotency:** money endpoints and job-creating endpoints require `Idempotency-Key` (UUID); repeated keys return the stored response; different body with same key → 409.
- **Long jobs:** return `202 {"job_id": "…"}`; `GET /jobs/{id}` (owner/admin only) and `GET /jobs/{id}/events` (SSE progress).
- **Timeouts:** every endpoint must finish in < 2 s p99 at target load; anything heavier is a job.
- **Money:** request/response fields end in `_paisa` (integers). **Dates:** ISO 8601 UTC.
- **Request size limits:** JSON bodies ≤ 256 KB (Nginx + app); uploads ≤ `MAX_UPLOAD_MB` via multipart on upload endpoints only.

### 10.2 Endpoints

Public endpoints (no session): `GET /health`, `GET /health/ready` (internal network only via Nginx), `GET /auth/csrf`, `POST /auth/register`, `POST /auth/login`, `POST /auth/password/forgot`, `POST /auth/password/reset`, `POST /auth/email/verify`, `GET /public/projects`, `GET /public/projects/{id}` (limited), `GET /public/developers/{id}` (limited, respects visibility), `GET /public/stats` (landing counters, cached). **Everything else requires a session.**

| Module | Method & path | Purpose | Allowed |
|---|---|---|---|
| Auth | POST `/auth/register` | Create account (role CLIENT/DEVELOPER) → status PENDING, sends email + OTP | Public |
| | POST `/auth/otp/send` · `/auth/otp/verify` | Phone verification | Session (PENDING ok) |
| | POST `/auth/email/verify` · `/auth/email/resend` | Email verification | Public / session |
| | POST `/auth/login` | Password (+ TOTP step for admins) → session; returns `redirect_to` by role | Public |
| | POST `/auth/login/totp` | Second factor for admins | Pre-auth token |
| | POST `/auth/logout` · `/auth/logout-all` | End session(s) | Session |
| | POST `/auth/password/forgot` · `/auth/password/reset` · `/auth/password/change` | Password flows | Public / session |
| | GET `/auth/sessions` · DELETE `/auth/sessions/{id}` | Device list, revoke | Session |
| | POST `/auth/step-up` | TOTP re-check for sensitive admin actions (valid 10 min) | Admin |
| | POST `/auth/totp/setup` · `/auth/totp/confirm` · `/auth/recovery-codes/regenerate` | Admin 2FA | Admin |
| Me | GET/PATCH `/me` · GET `/me/export` (job) · POST `/me/delete` (password + confirm phrase) | Account | Session |
| Profiles | GET/PATCH `/me/developer-profile` · PUT `/me/skills` · CRUD `/me/portfolio` · POST `/me/portfolio/{id}/images` | Developer profile | Developer |
| | CRUD `/me/certificates` · CRUD `/me/external-reviews` | Evidence for admin verification | Developer |
| | GET/PATCH `/me/client-profile` | Client profile | Client |
| | GET `/developers/{id}` | Full profile + reputation (role-aware fields) | Session |
| Skills | GET `/skills` | Taxonomy | Session |
| Tests | GET `/skill-tests` · POST `/skill-tests/{id}/attempts` · GET `/attempts/{id}` · POST `/attempts/{id}/answer` · POST `/attempts/{id}/submit` | Timed MCQ (server-side timer; questions without answers) | Developer |
| Coding | GET `/coding-challenges` · POST `/coding-challenges/{id}/runs` (practice) · POST `/coding-challenges/{id}/submissions` (scored, job) | Judge0 | Developer |
| Marketplace | GET `/projects/search?q=&skills=&budget_min=&budget_max=&deadline_max=&team_size=&role=&hours=&sort=` · GET `/projects/recommended` | Find work | Developer |
| Projects | POST `/projects` (DRAFT) · GET `/projects?mine=1` · GET/PATCH/DELETE `/projects/{id}` | Client CRUD (DELETE only DRAFT) | Client (own) |
| | PUT `/projects/{id}/slots` · PUT `/projects/{id}/milestones` · PUT `/projects/{id}/dependencies` | Plan editing (whole-set replace, validated) | Client (DRAFT) |
| | POST `/projects/{id}/plan/preview` | CPM preview without saving | Client |
| | POST `/projects/{id}/publish` · `/projects/{id}/extend-bidding` · `/projects/{id}/cancel` | Transitions | Client |
| | GET `/projects/{id}/plan` | Baseline + forecast + critical paths | Client, members, admin |
| | POST `/projects/{id}/plan-changes` · POST `/plan-changes/{id}/approve|reject` | Re-planning after start | Client, lead |
| Bids | POST `/projects/{id}/bids` · GET `/me/bids` · PATCH/DELETE `/bids/{id}` | Sealed bids | Developer |
| | GET `/projects/{id}/bids` | All bids with eligibility | Client (own), admin |
| | GET `/bids/{id}/explanation` | Why not selected | Bidder, admin |
| Formation | POST `/projects/{id}/formation-runs` (job; Idempotency-Key) | Run filter + PSO + exact + fairness + explanations | Client (own) |
| | GET `/formation-runs/{id}` | Result: team, breakdown, risks, top teams, cost of fairness, convergence, relaxations, verification | Client (own), admin |
| | POST `/formation-runs/{id}/confirm` | Create team + invitations | Client (own) |
| | POST `/formation-runs/{id}/verify` | Exact verification | Admin |
| Team | GET `/projects/{id}/team` | Members, roles, reputation summary | Client, members, admin |
| | POST `/invitations/{id}/accept|decline` | Respond | Invitee |
| | POST `/projects/{id}/team/lead` · POST `/projects/{id}/lead-change-requests` · POST `/lead-change-requests/{id}/approve|reject` · POST `/projects/{id}/team/lead/decline` | Lead management | Client / members / lead |
| | GET `/projects/{id}/repair` · POST `/repair-proposals/{id}/choose` · POST `/projects/{id}/slots/{slot}/reopen` | Team repair | Client |
| | POST `/team-members/{id}/leave` | Leave (reason required) | Member |
| Tasks | GET/POST `/milestones/{id}/tasks` · PATCH `/tasks/{id}` · POST `/tasks/{id}/move` (status, position) · DELETE `/tasks/{id}` (lead, not DONE) | Kanban | Lead create/assign; assignee move own |
| | POST/DELETE `/tasks/{id}/dependencies` · POST `/tasks/{id}/evidence` · GET/POST `/comments?target_type=&target_id=` · PATCH/DELETE `/comments/{id}` | Details | Members, client |
| Check-ins | GET/POST `/projects/{id}/checkins` | Weekly | Members (post), client (read) |
| Discussion | GET/POST `/projects/{id}/threads` · GET/POST `/threads/{id}/posts` | Project messaging | Client, members |
| Files | POST `/projects/{id}/files` (multipart) · GET `/projects/{id}/files` · GET `/files/{id}/download` (302 → short-lived signed URL) · DELETE `/files/{id}` | Files | Members, client |
| Monitoring | GET `/projects/{id}/dashboard` · GET `/projects/{id}/risks` · GET `/projects/{id}/activity` · POST `/projects/{id}/github/sync` (job) | Health & risks | Client, members, admin |
| Milestones | POST `/milestones/{id}/submissions` · POST `/submissions/{id}/approve` (rating) · POST `/submissions/{id}/request-changes` (reason, comment) | Review | Lead / client |
| Money | GET `/wallet` · GET `/wallet/transactions` · POST `/wallet/deposit` (simulated, Idempotency-Key) · GET `/me/earnings` | Wallet | Session |
| | POST `/milestones/{id}/escrow/fund` (Idempotency-Key) · GET `/projects/{id}/payments` | Escrow | Client |
| | POST `/milestones/{id}/split` · POST `/splits/{id}/agree|object` | Splits | Lead / members |
| Reviews | GET `/projects/{id}/reviews/pending` · POST `/projects/{id}/reviews` · GET `/projects/{id}/reviews` (after reveal) · POST `/reviews/{id}/contest` | Blind reviews | Participants |
| Reputation | GET `/developers/{id}/reputation` · GET `/me/reputation/history` · GET `/projects/{id}/post-mortem` | Reputation | Session (role-aware) / participants |
| Disputes | POST `/disputes` · GET `/disputes/{id}` · POST `/disputes/{id}/statements` · POST `/disputes/{id}/withdraw` | Disputes | Parties |
| Notifications | GET `/notifications` · POST `/notifications/{id}/read` · POST `/notifications/read-all` · GET/PUT `/notification-preferences` · GET `/notifications/stream` (SSE) | Notifications | Session |
| Jobs | GET `/jobs/{id}` · GET `/jobs/{id}/events` (SSE) | Async status | Requester, admin |
| Admin | GET `/admin/dashboard` · GET `/admin/users` · POST `/admin/users/{id}/suspend|restore` (reason) · POST `/admin/certificates/{id}/verify|reject` · POST `/admin/external-reviews/{id}/verify|reject` | Users | Admin |
| | GET `/admin/projects` · POST `/admin/projects/{id}/cancel` (step-up) | Projects | Admin |
| | GET `/admin/disputes` · POST `/admin/disputes/{id}/resolve` (step-up; outcome, reason ≥ 20 chars) | Disputes | Admin |
| | GET `/admin/flags` · POST `/admin/flags/{id}/confirm|dismiss` · GET `/admin/alerts` · POST `/admin/alerts/{id}/resolve` | Integrity | Admin |
| | GET `/admin/formation-runs` · POST `/admin/reputation/recalculate` (step-up, job) | Algorithms | Admin |
| | GET `/admin/analytics/fairness?from=&to=` · POST `/admin/analytics/simulate` (job) · GET `/admin/analytics/platform` | Analytics | Admin |
| | GET `/admin/settings` · PUT `/admin/settings` (step-up, reason, validated) · GET `/admin/settings/history` | Settings | Admin |
| | GET `/admin/audit?entity_type=&entity_id=&actor=` · GET `/admin/audit/verify` (hash chain check) | Audit | Admin |
| | CRUD `/admin/skills` · CRUD `/admin/question-bank` · CRUD `/admin/coding-challenges` | Content | Admin |
| Client analytics | GET `/me/client-analytics` | On-time rate, spend, revisions | Client |

### 10.4 Contract-first API (machine-verifiable)

The endpoint table above is a map, not the contract. **Before implementing any endpoint, Claude Code writes its contract**, and the gate verifies it:

1. **Pydantic schemas for every operation:** request body, path and query parameters (with bounds and enums), each success response, and each error the endpoint can return. `extra="forbid"` on all requests.
2. **Shared envelopes** (`schemas/common.py`), used by every endpoint:
   - `ErrorResponse {error: {code, message, fields?, request_id}}` for 400/401/403/404/409/413/415/422/423/429/503, with the `code` enum listing every domain error (e.g. `INVALID_STATE`, `VERSION_CONFLICT`, `BID_DEADLINE_PASSED`, `NOT_ELIGIBLE`, `RATE_LIMITED`).
   - `ValidationErrorResponse` (422) with `fields: {field_path: message}`.
   - `Page[T] {items: T[], next_cursor: string | null}`.
   - `JobAccepted {job_id, status, progress}` for 202 responses.
   - `StateTransitionError` (409) with `code = INVALID_STATE`, `current_state` and `allowed_actions`.
3. **Every operation in OpenAPI declares all its responses** (`responses=` in FastAPI) with at least one **example** for the success case and each error case. Example for `POST /api/v1/projects/{id}/bids`:
   - Request: `{"slot_id": "…", "price_paisa": 1800000, "days_needed": 20, "hours_per_week_committed": 20, "proposal": "…", "portfolio_item_ids": [], "expected_contribution": null}`
   - 201: `{"id": "…", "status": "ACTIVE", "eligibility": {"eligible": true, "reasons": [], "newcomer_rule_applied": true}, "version": 1, …}`
   - 401 `UNAUTHENTICATED` · 403 `ROLE_NOT_ALLOWED` (a client tried to bid) · 404 `NOT_FOUND` (project not visible) · 409 `INVALID_STATE` (bidding closed, with `current_state: "FORMING"`) · 409 `ALREADY_BID` · 422 `VALIDATION_ERROR` (`fields: {"price_paisa": "Must be at least ৳500"}`) · 429 `RATE_LIMITED`.
4. **Contract artifacts and checks:**
   - The generated `docs/api/openapi.json` is committed; the gate fails if the code's OpenAPI differs from the committed file without an accompanying change note in the phase plan.
   - A contract linter (`scripts/check_openapi.py`) fails if any operation lacks a declared 401/403/404/422 (where applicable), an example, a summary, or uses an untyped `dict`/`Any` field.
   - schemathesis (§16.5 step 11) validates every response against these schemas.
   - The frontend's typed client is generated from `openapi.json` (`openapi-typescript`), so frontend and backend can't drift.
5. In Plan Mode, each phase plan includes a table of the phase's endpoints with their request, response and error schemas, approved before coding.

### 10.3 Server-Sent Events

`/notifications/stream` and `/jobs/{id}/events`: cookie-authenticated; Origin must equal `PUBLIC_ORIGIN`; heartbeat every 20 s; server closes after 30 min (client reconnects with backoff); max 3 concurrent streams per user (Redis counter); events carry only ids/types and safe text, never other users' private data.

---

## 11. Background jobs and schedules

| Job | Trigger | Timeout | Retries |
|---|---|---|---|
| `formation.run` (filter, PSO, exact, fairness, comparison, risks) | API | 60 s | 0 (user re-runs) |
| `formation.explanations` | after run succeeds | 120 s | 1 |
| `formation.repair` | decline/expiry/leave | 60 s | 1 |
| `reputation.update_project` | project COMPLETED or dispute resolved | 60 s | 3 (idempotent per project) |
| `reputation.recalculate_all` | admin | 30 min | 0 |
| `integrity.scan` (R1–R4, B1–B3, self-dealing, trust refresh) | nightly 02:00 + on review submit (debounced) | 10 min | 1 |
| `monitoring.evaluate` (forecast snapshot, risks, team health) | every 15 min + on task/milestone events (debounced 30 s) | 60 s | 1 |
| `lifecycle.expire` (invitations, review windows, split deadlines, dispute evidence windows, auto-approvals, bidding deadlines, sessions cleanup) | every 5 min | 60 s | 1 |
| `checkin.reminders` | Mondays 10:00 Asia/Dhaka | 5 min | 1 |
| `github.sync` | every 6 h + manual (rate-limited) | 120 s | 3 with backoff; circuit breaker after 5 failures |
| `coding.judge` | submission | 30 s | 1 |
| `email.send` (outbox) | every 30 s | 30 s per email | 5 with exponential backoff |
| `export.user_data` | user request | 5 min | 1 |
| `analytics.simulate` | admin | 10 min | 0 |
| `maintenance.cleanup` (expired tokens, idempotency keys, orphan uploads > 24 h) | daily 03:00 | 10 min | 1 |

Rules: jobs are idempotent (natural keys or `idempotency_key`); each job records progress in `jobs`; RQ `job_timeout` set per job; workers run with `--max-jobs 500` then restart (memory hygiene); a job never trusts input from the queue without re-loading and re-authorizing entities from the DB.

---

## 12. Notifications and email catalogue

| Event | Recipients | In-app | Email |
|---|---|---|---|
| Account verification / password reset / new-device login | user | — | ✓ |
| New bid on your project (batched hourly) | client | ✓ | daily digest |
| Bidding deadline reached / too few bids | client | ✓ | ✓ |
| Team formation finished | client | ✓ | |
| Selected (invitation, 48 h) / replacement invitation | developer | ✓ | ✓ |
| Not selected (link to explanation) | developer | ✓ | |
| Invitation accepted/declined/expired | client | ✓ | |
| Project started / you are team lead / lead changed | team | ✓ | ✓ |
| Task assigned / mentioned in comment / blocker reported | member / lead | ✓ | |
| Check-in reminder | members | ✓ | ✓ |
| Risk opened (CRITICAL) | client, lead | ✓ | ✓ |
| Milestone submitted / auto-approval in 2 days | client | ✓ | ✓ |
| Milestone approved / changes requested | team | ✓ | ✓ |
| Payment released / reward / penalty | member | ✓ | ✓ |
| Split proposed / objection | members / lead | ✓ | |
| Review window opened / reviews revealed / review contested | participants | ✓ | |
| Reputation updated | developer | ✓ | |
| Dispute opened / statement added / resolved | parties, admin | ✓ | ✓ |
| Integrity flag / platform alert | admin | ✓ | |
| Certificate verified/rejected | developer | ✓ | |

Notification text never contains secrets or other users' private data; links are relative app paths validated against the route table.

---

## 13. UI and UX specification

The interface must look and feel like a polished commercial SaaS product: calm, professional, information-dense but uncluttered, with purposeful motion. Every screen has loading (skeletons), empty, error and success states; every action gives feedback within 100 ms.

### 13.1 Design tokens (`frontend/src/design/tokens.css`, mirrored in `tailwind.config.ts`)

**Colour — light theme (default)**

| Token | Hex | Use |
|---|---|---|
| `--bg` | `#F7F8FA` | App background |
| `--surface` | `#FFFFFF` | Cards, panels, dialogs |
| `--surface-2` | `#F1F5F9` | Subtle sections, table headers, Kanban columns |
| `--border` | `#E2E8F0` | Dividers, inputs |
| `--text` | `#0F172A` | Primary text |
| `--text-muted` | `#475569` | Secondary text |
| `--text-subtle` | `#64748B` | Captions, placeholders (only on white/bg, AA for ≥ 14px) |
| `--primary` | `#0F766E` | Brand teal: primary buttons, active nav, links, focus |
| `--primary-hover` | `#115E59` | |
| `--primary-soft` | `#E6F4F2` | Selected rows, soft badges, highlights |
| `--accent` | `#4F46E5` | Data visualisation (competency, performance), secondary charts |
| `--newcomer` | `#B45309` text on `#FEF3C7` | Newcomer badges, fairness dial |
| `--success` | `#047857` on `#ECFDF5` | Approved, paid, healthy |
| `--warning` | `#B45309` on `#FFFBEB` | Medium risks, slack eaten |
| `--danger` | `#BE123C` on `#FFF1F2` | Critical path, critical risks, destructive actions |
| `--info` | `#0369A1` on `#F0F9FF` | Neutral notices |
| `--chart-1..6` | `#0F766E #4F46E5 #D97706 #BE123C #0369A1 #64748B` | Chart series |

**Colour — dark theme** (toggle in settings; follows OS by default): `--bg #0B1220`, `--surface #111827`, `--surface-2 #1E293B`, `--border #273449`, `--text #E5E7EB`, `--text-muted #A1A1AA`, `--primary #2DD4BF` (text on primary `#042F2E`), `--primary-soft #0F2E2B`, status colours lightened to keep ≥ 4.5:1 contrast. Every token pair is contrast-checked by a unit test (`design/contrast.test.ts`).

**Typography:** Inter (400, 500, 600, 700), JetBrains Mono (code). Scale (px/line-height): 12/16 caption · 14/20 body-sm · 16/24 body · 18/28 lead · 20/28 h4 · 24/32 h3 · 30/38 h2 · 36/44 h1 (landing hero 48/56). Numbers in tables, stats and money use `font-variant-numeric: tabular-nums`. Money formatting: `৳12,500` (Bangladeshi grouping via `Intl.NumberFormat('en-IN')`). Dates: `12 Oct 2026`; relative times ("2 days ago") with full date in a tooltip.

**Spacing:** 4-px grid (4, 8, 12, 16, 20, 24, 32, 40, 48, 64). **Radius:** sm 6 · md 8 (inputs, buttons) · lg 12 (cards) · xl 16 (dialogs, hero cards) · full (badges, avatars). **Elevation:** `xs 0 1px 2px rgb(15 23 42 / .05)`, `sm 0 1px 3px … /.08`, `md 0 4px 12px … /.08`, `lg 0 12px 32px … /.12`; dark theme uses borders more than shadows. **Focus ring:** 2 px `--primary` + 2 px offset, always visible on keyboard focus (`:focus-visible`).

### 13.2 Motion system (`frontend/src/design/motion.ts`)

| Token | Value |
|---|---|
| `duration.fast` / `base` / `slow` / `page` | 120 / 180 / 280 / 220 ms |
| `ease.standard` | `cubic-bezier(0.2, 0, 0, 1)` |
| `ease.emphasized` | `cubic-bezier(0.3, 0, 0, 1)` |
| `ease.exit` | `cubic-bezier(0.4, 0, 1, 1)` |
| `spring.drag` | stiffness 500, damping 35 |
| `stagger.list` | 30 ms per item, max 8 items animated |

**Animation catalogue (implement as reusable variants):**

| Element | Animation |
|---|---|
| Buttons | hover: background colour 120 ms + 1 px lift (`translateY(-1px)`) + shadow xs→sm; press: `scale(0.98)` 80 ms; loading: label cross-fades to spinner, width locked to avoid layout shift |
| Icon buttons | hover background circle fade-in 120 ms |
| Cards | enter: fade + 8 px rise, 180 ms; hover (interactive cards): lift 2 px + shadow sm→md + border → primary 30% |
| Lists / tables | rows stagger in (30 ms); new row highlight: primary-soft background fades out over 1.2 s |
| Page transitions | content fade + 6 px rise 220 ms; sidebar stays static |
| Dialogs / sheets | overlay fade 180 ms; dialog scale 0.96→1 + fade; side sheet slide from right 280 ms emphasized |
| Toasts | slide in from bottom-right + fade; auto-dismiss 5 s with progress bar; pause on hover |
| Tabs | active indicator slides between tabs (layoutId) 180 ms |
| Sidebar collapse | width transition 220 ms; labels fade |
| Skeletons | shimmer gradient 1.4 s loop (disabled under reduced motion → static) |
| Stat numbers | count-up from previous value 600 ms (only on first view) |
| Progress bars / meters | width animates 400 ms emphasized |
| Gantt bars | grow from left on first render (staggered 40 ms); critical path pulses once (border glow) |
| Dependency graph | nodes fade in by topological layer; edges draw (stroke-dashoffset) 300 ms |
| PSO run | live convergence line draws as SSE progress arrives; swarm "particles" indicator (8 dots orbiting) while running |
| Team result | member cards flip in one by one (rotateX 8° → 0) 220 ms, newcomer card gets an amber glow pulse once |
| Kanban | drag lifts card (scale 1.03, shadow lg), placeholder slot animates, drop springs into place; column count badge bumps |
| Notifications bell | badge pops (scale 0.6→1 spring) on new count; bell wiggles once |
| Risk chips | CRITICAL chip pulses twice when it first appears |
| Form errors | field shakes 4 px twice (150 ms) + message fades in below |
| Success | check icon draws (stroke) 300 ms on payment release, approval, submission |

**Reduced motion:** honour `prefers-reduced-motion` and the in-app setting: disable transforms, scaling, shimmer, count-ups and drawing; keep ≤ 120 ms opacity fades only. Motion never blocks interaction or delays content more than 300 ms.

### 13.3 Component library (`components/ui` via shadcn/ui, styled with tokens)

Button (primary, secondary, outline, ghost, destructive, link; sizes sm/md/lg; icon-only with required `aria-label`; loading state) · Input, Textarea (counter), Select, Combobox (search), MultiSelect (skills), Checkbox, Radio group, Switch, Slider (with value label, keyboard steps), Date picker · Form field wrapper (label, hint, error, required marker) · Card, Stat card (value, delta, sparkline) · Badge (status colours), Newcomer badge, Risk chip (severity icon + text, never colour only) · Avatar (initials fallback; newcomer ring) · Tabs, Breadcrumbs, Pagination/infinite list · Data table (sticky header, sortable whitelisted columns, row selection, responsive collapse to cards) · Dialog, Alert dialog (destructive confirm requires typing the project title for cancellation), Sheet, Popover, Tooltip, Dropdown menu, Command palette (⌘K / Ctrl+K: navigate, search projects) · Toast · Skeletons per layout · Empty state (illustration-free: icon + title + one-line help + primary action) · Error state (retry, request id) · Stepper (wizard) · Timeline (activity feed) · Progress bar, Meter, Ring progress · Rating stars (keyboard accessible radio group) · File dropzone (drag + click, progress, type/size hints) · Code editor (CodeMirror) · Countdown timer (tests) · Charts: line, bar, radar (reputation), donut (budget) with table fallback.

**Domain composites (`components/`):** `Gantt` (SVG; baseline vs forecast; critical path in danger colour; today line; zoom week/month; keyboard focusable bars with tooltips; table view toggle) · `DependencyGraph` (SVG layered DAG via longest-path layering; critical edges emphasized; click node → milestone panel) · `KanbanBoard` (@dnd-kit, keyboard sensor; WIP counts) · `ReputationPanel` (six parameter meters + C/P + radar + "show evidence" accordions) · `TeamCard` (member, slot, price, days, contribution bars, newcomer badge) · `TeamComparison` (side-by-side table with best values highlighted) · `FairnessDial` (segmented control 0..k with live "cost of fairness" chip after run) · `PrioritySliders` (four sliders always summing to 100% with linked normalization; preset chips) · `ConvergenceChart` · `RiskList` (grouped by severity, expandable details, "what to do" hint) · `BudgetDonut` · `EscrowTimeline` (Not funded → Funded → In review → Paid/Frozen) · `SplitEditor` (percent inputs that must total 100%, evidence-based suggestion button) · `EvidenceList` · `WhyNotSelectedCard` · `CPMTable`.

### 13.4 Layout and navigation

- **App shell:** top bar 64 px (logo → role home; global search/command palette; "Next day"-style demo controls are never shown in production; notifications bell with unread badge; avatar menu: profile, settings, theme, sign out). Left sidebar 248 px (collapsible to 72 px icon rail, state remembered per user); content area max-width 1280 px, padding 24 px (32 px ≥ 1280). Breakpoints: sm 640, md 768, lg 1024, xl 1280. Below lg the sidebar collapses; below md the app switches to the mobile layout with a bottom tab bar, card lists and bottom sheets. The full responsive specification is in **§13.14**.
- **Sidebars:**
  - Developer: Dashboard · Find Projects · My Bids · My Projects · Skill Challenges · Profile & Portfolio · Reputation · Earnings · Notifications · Settings
  - Client: Dashboard · Create Project · My Projects · Teams · Payments · Disputes · Analytics · Notifications · Settings
  - Admin: Dashboard · Users · Projects · Team Formation Runs · Integrity Flags · Platform Alerts · Disputes · Reputation · Payments · Fairness Analytics · Content · Settings · Audit Log
  - Inside a project workspace (all participants): secondary tab bar — Overview · Tasks · Timeline · Milestones · Team · Check-ins · Files · Discussion · Payments · Evidence · Risks (+ Reviews and Post-mortem when completed; + Disputes when any). The team lead sees "Lead tools" actions (create tasks, submit milestone, propose split) in context.
- **Entry point:** the app starts at the homepage `/` (§13.11), never at login or sign-up. Logout returns to `/`.
- **Route guards:** unauthenticated → `/login?return_to=<validated path>`; wrong role → `/403`; PENDING users → `/verify`; suspended → signed out with message; admin without TOTP → `/admin/setup-2fa`.
- **Document titles:** `<Page> · DevSync`; every page has one `h1`; skip-to-content link.

### 13.5 Screen specifications

Format per screen: route · purpose · layout & components · key actions · states · motion · notes. Build every screen listed; the 12 MVP screens (§17, Phases 2–11) come first.

**Public**

1. **Homepage (landing)** `/` — the entry point of the whole app (guests always land here; signed-in users are redirected to their role home). The full section-by-section specification, motion rules, navigation rules and performance targets are in **§13.11**; build exactly that.
2. **Login** `/login` — email, password, show/hide toggle, "forgot password"; generic error "Email or password is incorrect"; lockout message with time; admins continue to `/login/totp` (6-digit input with auto-advance + recovery code link). Redirect by role or `return_to`.
3. **Register** `/register` — step 1 role cards (Client / Developer, animated selection); step 2 name, email, phone (+880 default), password with strength meter (zxcvbn) and breached-password check message; terms checkbox; step 3 → `/verify`.
4. **Verify** `/verify` — phone OTP (6 boxes, paste support, resend countdown 60 s) and email status (resend); progress checklist; continues to role dashboard once both verified.
5. **Forgot / Reset password** — same neutral message whether or not the email exists; reset form with strength meter; all sessions revoked on reset.
6. **Public project list** `/projects` and **public project** `/p/:id` — cards with title, budget range, team size, skills, deadline, "Sign in to bid".
7. **Public developer** `/d/:id` — headline, skills, reputation summary (C, P, newcomer badge), portfolio (if PUBLIC).
8. **Error pages** — 403, 404, 500 (with request id), offline banner, maintenance page.

**Developer**

9. **Dashboard** `/dev` — greeting; invitation banner(s) with countdown + Accept/Decline; stat cards (competency, performance or "Building your record", active projects, earnings this month); "Recommended for you" carousel; my active projects (progress ring, next deadline, risk chip); recent bid outcomes; newcomer checklist (verify phone/email, add portfolio, pass a skill test) until not a newcomer.
10. **Find Projects** `/dev/find` — search bar; filter panel (skills multi-select, budget range slider, deadline, role/slot, team size, hours/week) — filters in URL query; results grid of project cards (title, budget, team size, skills chips with your skills highlighted, deadline, bids count hidden — sealed); sort (newest, budget, deadline). Empty state suggests broadening filters.
11. **Project details** `/dev/projects/:id` — header (title, client name + client rating, budget, deadline, team size); description, requirements; slots with skills; milestone list with states and durations; mini Gantt preview; **Bid sheet** (slide-over): slot select (only your skills), price (৳), days needed, hours/week commitment, proposal (counter), optional portfolio items (pick ≤ 3) and expected contribution; live eligibility preview (calls filter dry-run: "This bid would be filtered out because…"); submit → success check animation. Edit/withdraw until deadline.
12. **My Bids** `/dev/bids` and **Bid detail** `/dev/bids/:id` — status timeline (Submitted → Evaluated → Selected/Not selected → Accepted); **Why not selected** card: main gap, actionable hint, price counterfactual ("At ৳18,400 or less you would have been selected"), filter reasons if filtered.
13. **My Projects** `/dev/projects` — active/completed tabs; each opens the workspace.
14. **Skill Challenges** `/dev/challenges` — list by skill with last score, next attempt date; **Timed test** `/dev/challenges/test/:attemptId` — one question per screen, options as large radio cards, question counter, countdown timer (turns amber < 60 s, danger < 15 s), progress bar, "Submit" with confirm; server is the source of time; on submit score card with animated ring + "added to your profile"; **Coding challenge** `/dev/challenges/code/:id` — statement panel, CodeMirror editor, Run (practice, sample tests visible) and Submit (scored, hidden tests), results list.
15. **Profile & Portfolio** `/dev/profile` — sections: basics, skills with level selectors, availability hours/week, GitHub username, portfolio items (drag to reorder, image uploads with crop preview), certificates (upload → "Pending admin verification"), external reviews (upload evidence → pending), visibility setting. Autosave with "Saved" indicator.
16. **Reputation** `/dev/reputation` — ReputationPanel (six parameters with plain labels: Expertise, Communication, Teamwork, Quality, Client diversity, Punctuality; C and P; optional overall display score clearly labelled); trend chart over projects; "Why did this change?" list from reputation log (old → new, inputs, reason); contribution history per project; newcomer explanation card.
17. **Earnings** `/dev/earnings` — available balance, pending (escrow for your milestones), history table (milestone, base, reward/penalty, date), filters; CSV export (server-generated, CSV-injection-safe).
18. **Notifications** `/notifications` — grouped by day, unread dot, mark all read, preferences link.
19. **Settings** `/settings` — profile basics, password change, sessions/devices (revoke), notification preferences, theme & reduced motion, data export, delete account (danger zone: password + type "DELETE").

**Client**

20. **Dashboard** `/client` — stat cards (active projects, open for bids, waiting for your approval with auto-approve countdown, wallet balance); project list with status, progress, forecast impact chip, risk chips; "Create project" primary action; recent activity.
21. **Create Project wizard** `/client/projects/new` — Stepper: (1) Information (title, summary, description) (2) Requirements (requirements text, start date) (3) Skills & team (slots: skill + count; team size auto-sums) (4) Milestones & dependencies (table editor: name, duration, share %, skills; "after" chips to set predecessors; live DependencyGraph preview; share total meter must reach 100%) (5) Budget & deadline (budget ৳, bonus pool toggle + %, platform fee shown, deadline days, bidding deadline) (6) Review & generate plan → CPM result (Gantt + critical path + table + warnings: cycle, shares ≠ 100%, duration > deadline). Draft autosaves; leaving with unsaved changes prompts. "Publish for bids" requires payment method verified.
22. **Project plan** `/client/projects/:id/plan` — DependencyGraph + Gantt + CPMTable; baseline vs forecast toggle when in progress; plan change requests.
23. **Bids** `/client/projects/:id/bids` — table: developer (avatar, newcomer badge), slot, price, days, hours/week, competency, teamwork, performance, eligibility (reasons), proposal preview (expand); filters by slot and eligibility. Bid count per slot vs needed; "Too few bids" banner with options (extend, lower standards, raise budget, reduce team, cancel).
24. **Team formation** `/client/projects/:id/formation` — left panel: PrioritySliders + presets; minimum standards sliders (performance, competency) with "x of y bids pass" live count; FairnessDial; "Form team" (Idempotency-Key). While running: progress (SSE), live ConvergenceChart, swarm indicator. Result: recommended team (TeamCards with contribution bars), stat row (team fitness, team price vs budget, expected completion, verification "Optimal"/gap %, cost of fairness), "Why this team?" panel (coverage, budget, schedule, newcomers, risks chips, runner-up comparison, relaxations), TeamComparison (top 3), not-selected summary count, "Recalculate team", "Confirm team and send invitations" (confirm dialog).
25. **Team** `/client/projects/:id/team` — invitations with countdowns and statuses; lead recommendation card (why) + selector + "Start project"; team repair panel when needed: impact summary (forecast delay, affected milestones, budget delta), ranked candidates (top 3) with comparison, "Invite replacement", or "Reopen slot / raise budget" options.
26. **Payments** `/client/payments` — per project: milestones with EscrowTimeline, amount, status (Not funded, Funded, In review, Paid, Frozen), "Fund escrow" (Idempotency-Key; confirm with amount + fee), bonus pool usage, payouts breakdown per milestone (base, reward/penalty with policy explanation), wallet + deposit (simulated).
27. **Disputes** `/client/disputes` — list + detail (claim, response, evidence, timeline, outcome).
28. **Analytics** `/client/analytics` — on-time rate, spend vs budget, revisions per milestone, team performance over projects.

**Project workspace (shared; role-aware actions)** `/w/:projectId/...`

29. **Overview** — progress ring, schedule progress bar (planned vs actual), budget donut (released, committed, remaining), forecast finish + deadline impact chip, team health badge, overall risk level, top 3 risks, upcoming milestone, recent activity feed.
30. **Tasks (Kanban)** — columns To do / In progress / Review / Done with counts; filters (milestone, assignee, my tasks); card: title, assignee avatar, deadline (danger when overdue), estimate, difficulty chip, dependency lock icon (blocked until dependencies done), evidence count, comment count; drag with keyboard support; task drawer: details, dependencies, files, evidence (add link/file/PR), comments with @mentions, activity. Lead: "New task" (title, milestone, assignee, deadline, estimate, difficulty, dependencies).
31. **Timeline** — Gantt with baseline vs forecast, critical path, today line; milestone panel on click.
32. **Milestones** — list with status, share, escrow state, revisions, submissions history; lead "Submit milestone" (description, choose evidence from tasks, files) → confirm; client review panel: rating stars, "Approve and release payment" (success animation), "Request changes" (reason select: misunderstood requirements, bugs, incomplete, design/quality, other + comment), "Open dispute"; auto-approval countdown visible to both sides.
33. **Team** — members with slot, lead badge, reputation summary, hours/week, contribution so far; lead change request; leave project (reason, confirm).
34. **Check-ins** — weekly form (done, next, blockers, confidence slider) for members; feed grouped by week; missing check-in warnings.
35. **Files** — list/grid, upload dropzone, linked task/milestone, uploader, size, download (signed URL), delete (uploader/lead).
36. **Discussion** — threads list + posts (plain text, @mentions, edit window 15 min with "edited" label); polling every 15 s while visible.
37. **Payments** — milestone escrow states, split editor (lead proposes with evidence suggestion; members agree/object), payouts per member with policy details.
38. **Evidence** — GitHub stats per member (merged PRs, reviews given, active days), activity evidence summary, sync button (rate-limited); note "evidence only; not used directly in reputation except communication and teamwork signals described in the Reputation page".
39. **Risks** — RiskList grouped CRITICAL/MEDIUM/LOW with details and suggested actions (e.g., "Find replacement", "Re-plan", "Message member").
40. **Reviews** (after completion) — blind status ("3 of 9 submitted"); your pending reviews: client rates each developer (overall + communication, quality, timeliness categories); developers rate teammates (overall + collaboration, reliability, help) and the client (overall + clarity, fairness, timely approvals); reveal state; contest button on reviews about you.
41. **Post-mortem** — planned vs actual (duration, budget), milestones table (planned/actual/revisions), critical delays with causes (from forecast snapshots), team changes, each member's reputation change with reasons.
42. **Disputes (project)** — open dispute form (category, claim, requested outcome, files); evidence auto-attached preview; statements thread; outcome.

**Admin**

43. **Dashboard** `/admin` — stat cards (users, active/completed projects, open disputes, open flags, alerts), worker distribution chart (newcomers vs experienced), fairness snapshot (newcomer share, Gini), recent alerts.
44. **Users** — search, filters (role, status), table; user detail: profile, reputation, projects, sessions, audit trail; suspend/restore (reason); verify certificates/external reviews (side-by-side file preview).
45. **Projects** — table with status, client, budget, risks; detail (read-only workspace view); cancel (step-up + reason).
46. **Team Formation Runs** — table (project, seed, team, fitness, exact best, gap, runtime, settings version); run detail (params, candidates snapshot, convergence, result, explanations); "Verify" button.
47. **Integrity Flags** — queue grouped by rule; detail with evidence graph (for R3: small node-link view), affected reviews, reputation before/after if confirmed; Confirm (with optional sanction) / Dismiss (reason).
48. **Platform Alerts** — list (suspicious bidding, unresolved disputes > 7 days, auto-approval spikes, repeated failed logins, job failures).
49. **Disputes** — queue; detail: disputed milestone and amount, client claim, developer response, evidence tabs (requirements, submissions & files, revisions, comments/discussion, approval history, task board snapshot, check-ins, GitHub), decision form (release full / partial % / refund / request revision / new split / remove review), written reason (≥ 20 chars), step-up TOTP; preview of ledger effects before confirming.
50. **Reputation** — search developer → full parameter breakdown + log; recalculate (step-up).
51. **Payments** — platform ledger overview, escrow totals, fees, bonus pools; transaction search; ledger balance check result.
52. **Fairness Analytics** — date range; newcomer share vs baseline, Gini, selection distribution histogram, cost of fairness distribution; "Run simulation" (job) comparing DevSync vs top-rated on simulated jobs.
53. **Content** — skills taxonomy, question bank (import/export CSV with validation), coding challenges.
54. **Settings** — grouped forms for §6.2 with validation and explanations; change reason required; version history with diff; step-up TOTP.
55. **Audit Log** — filterable table, hash-chain verification status.

### 13.6 Accessibility (WCAG 2.1 AA) and content rules

Keyboard access for everything (including Kanban drag via keyboard sensor and Gantt bars); visible focus; labels for every control; `aria-live="polite"` for toasts, job progress and form errors; charts have table alternatives; status never by colour alone (icon + text); minimum 44 × 44 px touch targets on mobile; respects reduced motion and 200% zoom without horizontal scrolling (except Gantt, which scrolls inside its container). Plain, friendly microcopy; every algorithmic result has a one-sentence explanation; destructive actions explain consequences; no dark patterns.

### 13.7 Frontend engineering rules

- Data fetching only via TanStack Query hooks in `features/*/api.ts`; query keys centralized; sensible `staleTime` per resource (lists 30 s, reference data 10 min); optimistic updates for task moves, comments, notifications read (with rollback).
- Forms via React Hook Form + Zod schemas that mirror backend validation; server field errors mapped to fields.
- Route-level code splitting (`lazy`), prefetch on hover for main nav links; bundle budget: initial JS ≤ 250 KB gzip, each route chunk ≤ 150 KB gzip, except the lazily loaded homepage 3D chunk (≤ 220 KB gzip, §13.12) (checked in the gate).
- No `dangerouslySetInnerHTML`, no `eval`, no inline event handlers in HTML, no external URLs; user text rendered as text (comments with simple linkification using a safe parser that only creates `https` links with `rel="noopener noreferrer nofollow"`).
- Fetch wrapper: credentials `same-origin`, CSRF header injection, 401 → redirect to login with `return_to`, 403 → toast + stay, 429 → toast with retry time, network errors → offline banner and retry with backoff (GET only).
- Images: lazy loading, explicit width/height to avoid layout shift.
- **Every screen is built mobile-first and checked at all target sizes before it is considered done (§13.14);** a screen that only works on a laptop is unfinished.

### 13.8 Visual quality bar (applies to every screen; checked at every demo readiness review)

The target look is a calm, modern SaaS product in the style of Linear, Stripe Dashboard and Vercel: generous white space, a clear hierarchy, restrained colour and crisp typography. Nothing should look like an unstyled framework default.

1. **Page header pattern (every page):** breadcrumb (when nested) → `h1` title (24/32, 600) → one-line description in `--text-muted` → primary action button on the right; optional tabs under the header. 24 px gap to content.
2. **Layout:** content sits in cards (`--surface`, radius 12, 1 px `--border`, shadow xs) on the `--bg` background; 24 px gutters; max two columns on dashboards at ≥ 1280 px (8/4 split), one column below 1024 px. Never more than three accent colours on one screen.
3. **Hierarchy:** one primary button per view; secondary actions use outline or ghost buttons; destructive actions use the danger style and always confirm.
4. **Numbers:** reputation parameters, competency, performance and thresholds are stored 0–1 but **shown as whole numbers 0–100** everywhere in the UI (e.g. "Teamwork 66"); team fitness is shown with two decimals; tabular figures; money as `৳12,500` (with `৳`, rendered with a font that has the glyph: Inter does); percentages with one decimal at most; durations as "4 days", dates as "2 Nov 2026"; very large counts abbreviated (12.4k).
5. **Tables:** 44 px rows, sticky header, zebra-free (use row hover instead), right-aligned numbers, status as badge (icon + text), row actions in a "⋯" menu, empty state inside the table frame.
6. **Charts:** no 3D, no gradients behind data; light grid lines (`--border`); labels in `--text-muted` 12 px; series colours from `--chart-*` in order; tooltips with exact values; every chart has a "View as table" toggle.
7. **Icons:** lucide, 16 px inline / 20 px in buttons and nav, stroke width 1.75, always paired with text except well-known icon buttons (close, more, search), which need `aria-label`.
8. **States:** every data view has skeleton (matching the final layout), empty (icon, one-sentence explanation, primary action), error (what happened, retry, request id) and success feedback (toast or inline confirmation). No raw error text, no spinners longer than 300 ms without a skeleton.
9. **Motion:** only the catalogue in §13.2; nothing bounces or loops except the PSO "swarm" indicator while a job runs.
10. **Consistency check:** before a demo, Claude Code produces `runs/demos/demo-N-gallery.html` (all screens in light and dark, desktop and mobile, from the Playwright run) so the student can review them side by side; fix inconsistencies before the presentation.

### 13.9 Key screen layouts for Demos 1 and 2

These wireframes fix the structure of the screens that earn the most marks. Follow them; adjust spacing and details with the design tokens. Numbers shown are illustrative except where they come from the seed data (§18.4).

**Landing page (Demo 1)**
```
[logo DevSync]                         [Find work] [Hire a team] [Sign in]
┌──────────────────────────────────────────────────────────────────────────┐
│  Plan the project. Hire a fair team.        ┌──────────────────────────┐ │
│  Watch the work. Learn from it.             │ animated loop:           │ │
│  one-line description                       │ Plan → Form team → Work  │ │
│  [Hire a team]  [Find work]                 │ → Pay → Learn            │ │
└──────────────────────────────────────────────────────────────────────────┘
 [Fair team formation] [Transparent selection] [Evidence-based reputation]
 [Milestone payments]  [Monitoring, not surveillance]          (5 value cards)
 Stats strip: projects · developers · % newcomers hired      Research credit
```

**Client dashboard (Demo 1 → richer in Demo 2)**
```
Good afternoon, Rahim                                      [+ Create project]
[Active projects 3] [Open for bids 2] [Awaiting your approval 1 · auto in 4d] [Wallet ৳85,000]
┌ My projects ─────────────────────────────────┐ ┌ Recent activity ─────────┐
│ Title        Status     Progress  Forecast  Risk│ │ • Nadia placed a bid    │
│ Ordering sys Bidding    —         —         —   │ │ • Milestone 2 submitted │
│ Inventory    In progress ███░ 62% +2 days  ● Crit│ │ • Team formed           │
└───────────────────────────────────────────────┘ └──────────────────────────┘
```

**Create project — milestones step (Demo 1)**
```
Stepper: Info ✓ · Requirements ✓ · Skills & team ✓ · ● Milestones · Budget · Review
┌ Milestones ───────────────────────────────────┐ ┌ Dependency preview ──────┐
│ Name            Days  Share  Skills    After   │ │  [Req]→[DB]→[API]→[Int]  │
│ Requirements      4    10%   UI/UX     —       │ │     ↘[Frontend]↗   →[QA] │
│ Database          5    15%   Postgres  Req     │ │ critical path in rose    │
│ … [+ Add milestone]                            │ └──────────────────────────┘
│ Share total ████████████ 100% ✓                │
└────────────────────────────────────────────────┘        [Back] [Continue]
```

**CPM planner / plan page (Demo 1)**
```
Online ordering system · Plan                    [Gantt | Table]  [Zoom: Week]
Summary chips: Duration 24 days · Critical milestones 5 · Finish 6 Nov
┌ Gantt ───────────────────────────────────────────────────────────────────┐
│ Requirements  ████                                   (critical = rose)  │
│ Database          █████                                                  │
│ Frontend          █████████ ░░░░ slack 4d                                │
│ Backend API            ████████                                          │
│ …                       today ┆                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Bids table (Demo 1)**
```
Bids · Online ordering system        Slots: React 2/1 ✓ · FastAPI 3/1 ✓ · Testing 1/1 ✓
Filters: [Slot ▾] [Eligibility ▾]                               12 bids · 9 eligible
Developer           Slot     Price    Days  C     Xm    P     Eligibility
(N) Nadia Rahman    React    ৳18,000  20    31    50    —     ✓ Eligible (newcomer rule: React test 85%)
Arif Hossain        FastAPI  ৳28,000  18    80    77    80    ✓ Eligible
Shakib Hasan        FastAPI  ৳22,000  31    59    55    56    ✗ Can't meet deadline (31 > 30 days)
```

**Team formation (Demo 2 — the centrepiece)**
```
┌ Settings (left, 340 px) ─────┐ ┌ Result ───────────────────────────────────────┐
│ Preset: [Balanced][Budget]   │ │ Stat row: Fitness 0.71 · ৳96,500 of ৳114,000 │
│         [Quality][Fast]      │ │ · Finish in 22 days · ✓ Optimal (exact check) │
│ Competency ───●──── 35%      │ │ · Cost of fairness 3.2%                        │
│ Teamwork   ──●───── 25%      │ │ [TeamCard][TeamCard][TeamCard (N)][TeamCard]   │
│ Speed      ─●────── 20%      │ │ ┌ Why this team? ─┐ ┌ Convergence chart ─────┐ │
│ Cost       ─●────── 20%      │ │ │ coverage, budget│ │  line rising to plateau │ │
│ Min performance ──●── 45     │ │ │ risks, runner-up│ └────────────────────────┘ │
│ Newcomers at least: [0][1][2]│ │ └─────────────────┘  Compare top 3 teams ▸     │
│ [Form team]                  │ │ [Recalculate]            [Confirm & invite ▸]  │
└──────────────────────────────┘ └───────────────────────────────────────────────┘
```

**Workspace overview (Demo 2)**
```
Inventory dashboard   [Overview][Tasks][Timeline][Milestones][Team][Check-ins][Files][Payments][Risks]
[Progress ring 62%] [Schedule: planned 70% vs actual 62%] [Budget donut] [Forecast: 25 days (+2)] [Health: At risk]
┌ Top risks ─────────────────────────┐ ┌ Upcoming milestone ┐ ┌ Activity ──────┐
│ ● CRITICAL Dashboard frontend late │ │ Integration · day 18│ │ • task moved   │
│   pushes deadline by 2 days  [Act] │ └────────────────────┘ │ • check-in     │
│ ● MEDIUM Inventory API slack used  │                        └────────────────┘
└────────────────────────────────────┘
```

**Kanban (Demo 2)**
```
Milestone [Dashboard frontend ▾]  Assignee [All ▾]  [Only mine]          [+ New task] (lead)
To do (3)          In progress (2)       Review (1)          Done (5)
┌─────────────┐    ┌─────────────┐       ┌─────────────┐     ┌─────────────┐
│ Chart widget│    │ Stock table │       │ Login page  │     │ API client  │
│ 👤RT  ⏱6h  M │    │ 👤RT due 3d │       │ 👤SB ⛓ 2 ev │     │ ✓           │
└─────────────┘    └─────────────┘       └─────────────┘     └─────────────┘
```

**Milestone review and payment (Demo 2)**
```
Milestone 2 · UI design · Submitted 2 days ago · auto-approves in 5 days
Evidence: 4 files · 2 links · 3 pull requests                     Escrow: ৳17,100 Funded
Rating ☆☆☆☆☆   [Approve and release payment]  [Request changes ▾]  [Open dispute]
After approval → Payouts: Raisa ৳9,400 (+৳620 reward) · Salwa ৳7,700 · policy details ▸
```

**Reputation page (Demo 2)**
```
Your reputation                                   Newcomer · 1 of 3 projects done
[Expertise 42][Communication 71][Teamwork 66][Quality 80][Client diversity 50][Punctuality 55]
Competency 62 · Performance 64          [Radar chart]   [Trend over projects]
Why did this change?  Project "Inventory": Punctuality 50 → 55 (finished 2 days early) ▸
```

### 13.10 Content and microcopy style

Plain, friendly and specific; second person ("your bid"); sentence case for all labels and headings; verbs on buttons ("Form team", "Approve and release payment", never "Submit" or "OK"); numbers instead of vague words ("2 days late", not "delayed"); every algorithmic result has one sentence of "why" in plain language; errors say what happened and what to do next; no jargon on user screens (say "cost of fairness", "teamwork", "punctuality", not "fitness term C3" or "Eq. 11") — paper terms appear only in admin and developer explanation drawers.

### 13.11 Homepage (landing page) — full specification

**DevSync always opens on this homepage, like Upwork or Fiverr: never on the login or sign-up page.** It is the front door from which every public path starts, and the first screen of every demo, so it must look polished, move beautifully and load fast.

**Entry and navigation rules**
- `/` shows the homepage to guests. Signed-in users who open `/` are redirected to their role home (`/client`, `/dev`, `/admin`), as on real freelancing platforms; clicking the logo inside the app goes to that role home.
- Every public route is reachable from the homepage: **Sign in** → `/login`, **Get started** → `/register`, **Hire a team** → `/register?role=client` (role preselected), **Find work** → `/register?role=developer`, **Browse projects** → `/projects`, plus in-page anchors (How it works, Features, For clients, For developers, FAQ) and the footer (privacy, terms, research credit).
- Login and register pages show the DevSync logo, which links back to `/`, and a "Back to home" link. After login, users go to their role home or a validated `return_to` (§14.6); after logout they return to `/`, not to the login page.
- Unknown public paths show a friendly 404 with links back to the homepage.

**Sections, top to bottom**
1. **Navigation bar (sticky):** logo · How it works · Features · For clients · For developers · Browse projects · [Sign in] · [Get started] (primary). Transparent over the hero and becomes a solid, blurred surface with a hairline border after 24 px of scroll (200 ms transition); hides on fast scroll-down and reappears on scroll-up. On mobile it collapses into a menu button that opens a full-height sheet with staggered links.
2. **Hero:** headline "Plan the project. Hire a fair team. Watch the work. Learn from it." revealed **word by word** (40 ms stagger, 8 px rise, blur 4 px → 0); one-line subheading fades in after it; two buttons (Hire a team, Find work) with a gentle glow on the primary; a soft animated gradient-mesh background in brand teal and indigo that drifts slowly (CSS animation, 20 s loop, very low contrast). On the right, the **3D "talent constellation"** (React Three Fiber, full specification in **§13.12**): glowing developer nodes slowly rotate and, as the user scrolls, snap into a four-person team with the newcomer glowing amber and a "✓ Optimal team · cost of fairness {x}%" chip. A pre-rendered poster shows instantly and the live scene fades in once loaded. It conveys the PSO idea without any jargon.
3. **Trust and stats strip:** three or four live numbers from `/public/stats` (projects planned, developers, newcomers hired, average on-time rate) that **count up** when they scroll into view, plus "Based on published research from the University of Dhaka". If the stats are empty (new install), show the research line only, never zeros.
4. **How it works (scroll-driven):** five steps: Plan → Form a fair team → Work → Pay by milestone → Learn. On desktop a sticky left column lists the steps and highlights the active one while the right side swaps an illustration for each step as the user scrolls (Framer Motion `useScroll`). Each illustration animates once: Gantt bars growing with the critical path turning rose; dots converging into a team; Kanban cards sliding between columns; an escrow badge going Funded → Paid with a check-mark draw; a reputation radar expanding. On mobile it becomes a vertical timeline with each step fading in.
5. **Feature showcase:** three alternating image-and-text rows (team formation with explanations; monitoring and risk alerts; milestone payments and evidence-based reputation), each with a small looping UI animation built from real components with seeded sample data (not screenshots), so they stay sharp and match the app.
6. **For clients / For developers:** a segmented toggle with a sliding indicator that swaps two benefit lists with a cross-fade (clients: plan in minutes, fair teams within budget, early delay warnings, pay only for approved work; developers: a fair first chance for newcomers, see why you weren't picked, reputation from real work, fair payment splits). Each list ends with the matching call to action.
7. **Fairness spotlight:** a short explanation of the newcomer problem with an interactive "fairness dial" demo: moving the slider from 0 to 2 newcomers updates a small team preview and the cost-of-fairness chip, using the values computed from the sample project (see "Homepage figures are never invented" below; no server call), labelled as an example. It is the most memorable section and should feel playful.
8. **Research credit:** a calm card citing the two papers with links, a line stating that DevSync implements and extends them, and the supervisor's name.
9. **FAQ:** 5–6 questions in an accordion with smooth height animation (Is it free? Is the money real? How are teams chosen? How do newcomers get selected? Is my work monitored? How are fake reviews handled?). The answer to "Is the money real?" says clearly that payments are simulated.
10. **Final call to action:** a full-width band with the brand gradient, headline "Ready to build your next project?", and both buttons; a subtle shimmer passes across the primary button every 6 seconds.
11. **Footer:** logo and tagline, column links (Product, For clients, For developers, Research, Legal), course credit (CSE 3102, University of Dhaka), copyright line.

**Motion rules for the homepage** (in addition to §13.2):
- Use Framer Motion for reveals and scroll effects and SVG for illustrations; the **only** WebGL on the site is the hero scene in §13.12 (React Three Fiber, lazy-loaded, with a poster fallback). No other 3D or animation libraries, no autoplaying video, no external assets (CSP §14.3; everything is bundled).
- Section content reveals once when 20% visible (fade + 16 px rise, 350 ms, stagger 60 ms); nothing re-animates on every scroll.
- Hover micro-interactions on cards (lift 4 px, shadow grows, icon tilts 6°) and buttons (§13.2).
- Animations pause when their section is off screen or the tab is hidden (`IntersectionObserver`, `visibilitychange`) to save CPU and battery.
- With `prefers-reduced-motion` (or the in-app setting): no word-by-word reveal, no drifting background, no swarm movement (show the final converged state), no count-ups (show final numbers), no parallax; simple 120 ms fades only.
- Smooth anchor scrolling with an offset for the sticky navbar; "back to top" button after two screens of scrolling.

**Performance and quality targets (homepage)**
- Lighthouse on the production build: Performance ≥ 90, Accessibility ≥ 95, Best practices ≥ 95, SEO ≥ 90 (desktop and mobile profiles).
- Largest Contentful Paint < 2.0 s, Cumulative Layout Shift < 0.05, Interaction to Next Paint < 200 ms on a mid-range laptop; animations hold 60 fps (checked with the Playwright performance trace).
- The homepage chunk is loaded first; sections below the fold and the swarm animation are lazy-loaded; fonts are preloaded with `font-display: swap`.
- Proper metadata: title, description, Open Graph tags and a social preview image generated at build time; `robots.txt` allows the homepage and public projects and disallows `/admin` and `/api`.
- Fully responsive (390, 768, 1024, 1440 px), keyboard-navigable, one `h1`, every animated illustration has a text alternative.

**Homepage figures are never invented (rule 0.2.6).** Every number shown on the homepage, including the "cost of fairness {x}%" chip in the hero, the values in the fairness-dial demo and the example team, comes from a **real run of DevSync's own algorithms** on the sample project from the seed data: `scripts/build_homepage_example.py` runs filtering, PSO (fixed seed) and the fairness computation for newcomer minimums 0, 1 and 2, and writes `frontend/src/content/homepage-example.json`, which the homepage reads at build time. These figures are labelled **"Example from a sample project"** in small text next to them. Live statistics come only from `/public/stats`. The gate re-runs the script and fails if the JSON is out of date.

### 13.12 Homepage 3D hero scene (React Three Fiber)

The homepage uses **one** real-time 3D scene, in the hero, to make a strong first impression. Everything else on the homepage uses Framer Motion and SVG in the same visual language, and **no other page uses WebGL**.

**Concept — "the talent constellation".** A slowly rotating constellation of about 48 glowing developer nodes (small spheres) connected by faint lines floats on the right side of the hero. Every few seconds a soft pulse travels along the lines. As the user scrolls the first 600 px (or after 6 seconds without scrolling), the nodes drift together and **snap into a team**: four nodes move to the front, brighten and link with solid lines; one of them glows amber (the newcomer included by the fairness dial); a small HTML chip anchored to the team (Drei `Html`) fades in: "✓ Optimal team · cost of fairness {x}%". Scrolling back up releases them into the constellation. The pointer gently tilts the scene (at most 6°, damped). The concept tells DevSync's story (many developers → a fair, balanced team) without any text.

**Visual style (shared with the whole app)**
- Colours only from the design tokens: nodes in `--primary` teal and `--accent` indigo, the newcomer node in the `--newcomer` amber, lines in a low-opacity version of `--text-subtle`; background transparent so the hero's gradient mesh shows through. Both light and dark themes are supported (node brightness and line opacity come from the theme).
- Soft "studio" lighting: one ambient light, one key directional light and two Drei `Lightformer`s inside an `Environment` (generated locally; **never** a remote HDR file, which the CSP would block anyway). Materials: `MeshStandardMaterial` with a slight emissive glow; glass and transmission effects are not used (too heavy).
- Optional soft bloom through `@react-three/postprocessing` **only** if the performance budget below is still met; otherwise the glow comes from emissive materials and additive sprites.
- Motion timing follows §13.2: slow, eased, never bouncy; the constellation completes one rotation in about 60 s.

**Technology**
- `three` (r160 or newer, pinned), `@react-three/fiber`, `@react-three/drei` (and optionally `@react-three/postprocessing`). No other 3D or animation libraries (no GSAP, no Babylon.js, no Spline runtime). Framer Motion remains the only UI animation library.
- Geometry is generated in code: `InstancedMesh` for the nodes (one draw call), `LineSegments` with a buffer geometry for the links; no 3D model files, no textures larger than 256 px, no 3D text.

**Performance guardrails (must hold; checked in the Phase 2 gate)**
- **Poster first:** the hero shows a pre-rendered still image of the scene (`hero-poster.webp`, generated by `npm run render:stills`, below) immediately. The 3D chunk is loaded lazily after first paint (`requestIdleCallback` once the hero is visible), then the live canvas cross-fades over the poster (400 ms). The **Largest Contentful Paint element is the headline text**, never the canvas.
- Separate lazy chunk for all 3D code, **≤ 220 KB gzip** (the only exception to the §13.7 route budget); the homepage's initial JavaScript must stay within the normal budget.
- `dpr={[1, 1.5]}`; antialiasing on; no shadows; at most 60 nodes and about 20,000 triangles in total; one canvas only.
- Drei `PerformanceMonitor`: if the frame rate stays below 50 fps, lower the DPR to 1 and switch off bloom and the pulse effect; if it stays below 30 fps, stop the animation and keep the last frame (poster quality).
- Render only when needed: pause the render loop when the hero is off screen (`IntersectionObserver`) or the tab is hidden; release WebGL resources when leaving the homepage.
- **Fallbacks (always show the poster, no canvas):** `prefers-reduced-motion` or the in-app reduced-motion setting, WebGL unavailable or a lost context, the browser's data-saver mode, or a device with fewer than 4 logical CPU cores.
- The canvas is decorative: `aria-hidden="true"`, with a visually hidden text description of the idea next to it; keyboard focus never enters it.
- Homepage targets from §13.11 still apply with the 3D scene on: Lighthouse Performance ≥ 90 on the desktop profile and ≥ 80 on mobile, LCP < 2.0 s, CLS < 0.05, and a steady 60 fps on the demo laptop (measured with the Playwright performance trace).

### 13.13 One look across the whole app (consistency system)

- **Single source of truth:** design tokens (§13.1) drive Tailwind, CSS variables **and** the 3D scene (a `tokens.ts` export read by the scene), so colours always match across 2D and 3D, light and dark.
- **Still renders of the 3D elements for in-app use:** `npm run render:stills` (a Playwright script that opens a hidden `/__stills` route in development builds only) renders the constellation and the "team" moment in light and dark at 1x and 2x and saves optimised WebP files in `frontend/src/assets/stills/`. These stills give the rest of the app the same identity without any WebGL cost: the login and register pages (soft, blurred constellation on the side panel), empty states (for example "No projects yet"), onboarding cards, the 404 page and the social preview image. Re-run the script whenever the scene or tokens change; the gate checks that the stills are up to date (hash of scene file + tokens recorded in the stills manifest).
- **Shared illustration language:** every 2D illustration on the homepage and in empty states uses the same node-and-line motif, the same palette and the same rounded geometry, so the 3D hero, SVG diagrams and in-app visuals look like one family.
- **Motion consistency:** all UI motion uses the variants in `design/motion.ts` (§13.2); no ad-hoc durations or easings in components (an ESLint rule flags numeric `duration` values outside `motion.ts`).
- **Component consistency:** every page uses the page-header pattern and card layout from §13.8 and components from `components/ui`; no one-off styled buttons, inputs or modals (code review and the screen gallery in §13.8 check this before each demo).
- The `devsync-ui` skill (§0.4) documents all of this, so Claude Code applies it automatically on every page.

### 13.14 Responsive design (laptop and mobile equally polished)

Every screen must feel **designed** for each device, not merely shrunk. Mobile users get the same features as laptop users (nothing is "desktop only"), with layouts and interactions adapted to touch and small screens.

**Approach and breakpoints**
- Mobile-first CSS with Tailwind breakpoints: `sm` 640, `md` 768, `lg` 1024, `xl` 1280, `2xl` 1536 px.
- **Target devices (all must look right):** 360×740 (small Android), 375×667 (iPhone SE), 390×844 (iPhone 14), 412×915 (Pixel 7), 768×1024 (tablet portrait), 1024×768 (tablet landscape), **1366×768 (the most common laptop size here; must not feel cramped)**, 1440×900, 1920×1080 (content centred, max width 1280 px with balanced margins).
- Phone landscape (e.g. 844×390) must remain usable: compact header, scrollable content, no fixed elements covering more than 20% of the height.

**Fundamentals**
- Fluid typography: headings use `clamp()` between the mobile and desktop sizes of §13.1 (e.g. h1 `clamp(1.75rem, 1.2rem + 2vw, 2.25rem)`); body text never below 16 px on mobile.
- Form inputs use a 16 px font on mobile, so iOS doesn't zoom in on focus; the correct `inputmode`, `autocomplete` and `enterkeyhint` on every field (numeric keypad for OTP and money, email keyboard for email).
- Touch targets at least **44×44 px** with 8 px spacing; no feature depends on hover (hover effects are an enhancement; every hover-only tooltip also opens on tap or focus).
- Use dynamic viewport units (`100dvh`) instead of `100vh`; respect safe areas (`env(safe-area-inset-*)`) for notches and home indicators; the viewport meta tag has `viewport-fit=cover`.
- No horizontal page scrolling at any width; only deliberate scroll areas (Gantt, Kanban, wide tables) scroll sideways, with visible scroll hints (edge fade + scrollbar).
- Images and stills use `srcset`/`sizes` and explicit dimensions; icons stay 20 px on mobile.
- Sticky elements (headers, action bars) must not overlap content or the on-screen keyboard: when the keyboard opens, the sticky action bar moves above it or hides.

**Navigation by size**
- **≥ 1024 px:** top bar + collapsible sidebar (§13.4).
- **768–1023 px:** top bar + sidebar collapsed to an icon rail by default.
- **< 768 px:** compact top bar (logo, search icon, notifications, avatar) + a **bottom tab bar** with the 4 most-used destinations for the role (Client: Home, Projects, Payments, More; Developer: Home, Find work, My projects, More; Admin: Dashboard, Disputes, Flags, More); "More" opens a full-height sheet with the rest of the sidebar. Inside a project workspace the tabs become a horizontally scrollable tab strip under the header, with the active tab kept in view.
- The homepage navbar becomes a menu button that opens a full-screen sheet (§13.11).

**Component adaptations (mobile < 768 px unless stated)**

| Component | Laptop | Mobile |
|---|---|---|
| Page header | Title, description and primary action in one row | Title and description stacked; primary action becomes a full-width button below, or a floating action button where the page has one main action (e.g. "New task") |
| Data tables | Table with sticky header | Card list: each row becomes a card with the 3–4 most important fields, a status badge and a "⋯" menu; sorting and filters move into a bottom sheet |
| Dialogs | Centred modal | Full-height bottom sheet with a drag handle, swipe down to close, sticky footer buttons |
| Forms and the create-project wizard | Two columns where helpful | One column; the stepper becomes "Step 3 of 6" with a progress bar; sticky bottom bar with Back / Continue; the milestones table becomes stacked editable cards with an "Add milestone" button; the dependency preview becomes a collapsible section |
| Gantt and CPM | Full Gantt with zoom | Defaults to the **CPM table/list view** (each milestone as a card with dates, slack and a critical badge); "Show timeline" opens the Gantt in a horizontally scrollable area with a sticky milestone-name column and zoom buttons (no pinch required) |
| Dependency graph | Full SVG | Fits the width with tap-to-focus on a node; a list of dependencies below it as the accessible alternative |
| Kanban board | All columns side by side | One column per screen with **horizontal snap scrolling** and column tabs at the top; drag uses long-press (300 ms) with auto-scroll at the edges; every card also has a "Move to…" menu so moving never depends on dragging |
| Team formation | Settings panel on the left, results on the right | Results first; settings in a bottom sheet opened by a "Adjust priorities" button; preset chips scroll horizontally; slider thumbs at least 28 px; team cards stack vertically; the convergence chart and comparison table move into collapsible sections |
| Dashboards | 8/4 two-column grid, 4 stat cards in a row | One column; stat cards in a 2×2 grid; charts at full width with simplified axes (fewer ticks) |
| Charts | Full charts with legends | Legend under the chart, tap shows the tooltip, "View as table" always available |
| Discussion and comments | Side panel or inline | Full-screen thread with the input fixed above the keyboard |
| Admin console | Tables with detail side panel | Card lists with the detail opening as a full screen; dispute evidence tabs become a scrollable tab strip |
| Homepage 3D hero (§13.12) | Live scene beside the headline | Headline first, scene below it at reduced density (about 24 nodes, `dpr` 1); falls back to the poster on low-end phones as in §13.12 |

**Performance on mobile:** Lighthouse mobile profile ≥ 80 for the homepage and ≥ 85 for app pages; no animation drops below 50 fps on a mid-range Android phone; lists longer than 50 items are virtualized.

**How responsiveness is verified (in every phase that builds screens)**
1. **Viewport matrix in Playwright:** every built screen is opened at 375×667, 390×844, 768×1024, 1366×768 and 1440×900, in light and dark mode. Each run asserts: no horizontal overflow (`document.documentElement.scrollWidth <= innerWidth`), no element overlapping another interactive element, all interactive elements at least 44×44 px on touch viewports (a script measures them), and no text clipped by its container.
2. **Visual baselines** at 390, 768 and 1440 px for every screen (§16.5 step 15).
3. **Mobile E2E flows:** the demo walkthroughs (§17.0) also run on the 390×844 touch profile, including Kanban moves via long-press and via "Move to…", the team formation bottom sheet and the create-project wizard.
4. **Real-device check before each demo:** `make demo-up` also serves on the local network with a trusted certificate (mkcert root installed on the phone), so the student opens the app on an actual phone; any issue found is fixed before the presentation.
5. The screen gallery (§13.8) shows each screen at mobile, tablet and laptop sizes side by side.

---

## 14. Security architecture

Security is implemented across all phases (§14.13). Each control has tests in `backend/tests/security/` or `e2e/security/`. `docs/SECURITY.md` is written from this section.

### 14.1 Assets

User accounts and sessions; personal data (email, phone, profile); money balances and the ledger; reputation and reviews (integrity); sealed bids (confidentiality until formation); project content and files; admin powers; platform settings; audit log; secrets (SECRET_KEY, DB/Redis passwords, GitHub token, Judge0 token).

### 14.2 Threat model (STRIDE summary; full table in `docs/SECURITY.md`)

| Threat | Examples | Main controls |
|---|---|---|
| Spoofing | Credential stuffing, session theft, fake accounts | Argon2id, breached-password check, lockout + rate limits, phone uniqueness, HttpOnly cookies, admin TOTP, new-device alerts |
| Tampering | Editing reviews/ledger, mass assignment, IDOR updates, replayed requests | Central authorization, `extra="forbid"` schemas, append-only tables + triggers, hash-chained audit, idempotency keys, optimistic concurrency |
| Repudiation | "I never approved that payment" | Audit log with request ids, actor, IP, before/after |
| Information disclosure | Seeing others' bids, private files, enumeration, verbose errors, logs | Sealed-bid authorization, signed short-lived file URLs, uniform auth errors, safe error handler, log redaction |
| Denial of service | Login floods, huge uploads, expensive PSO runs, slowloris, regex DoS | Nginx + app rate limits, size limits, timeouts at every layer, job quotas, bounded algorithms, no user-supplied regex |
| Elevation of privilege | Role tampering, admin endpoints, sandbox escape, XSS → admin actions | Server-side roles only, step-up TOTP, CSP, Judge0 isolation, no docker socket in app containers |
| Fraud/abuse (business) | Fake reviews, collusion, shill bids, self-dealing, review revenge | §9.14–§9.15 rules, blind reviews, trust weighting, admin review |

### 14.3 Transport and HTTP security

- TLS 1.2+ only (TLS 1.3 preferred) at Nginx; modern cipher suites; HTTP → HTTPS 301; HSTS `max-age=31536000; includeSubDomains` (+ preload in production docs).
- Security headers on every response (Nginx `security-headers.conf` + FastAPI middleware for API responses):
  - `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'; upgrade-insecure-requests` (no `unsafe-inline`, no `unsafe-eval`; Vite build configured accordingly; Tailwind/shadcn styles are in CSS files).

**CSP and the UI libraries (decide in the first task of Phase 2).** The strict `style-src 'self'` blocks `<style>` elements injected at runtime. Styles set from JavaScript through the DOM (`element.style`, which React, Framer Motion, Radix positioning and React Three Fiber use) are **not** affected. So:
- **Avoid components that inject `<style>` tags:** use shadcn's **Radix-based Toast** instead of Sonner; use native `overflow: auto` with styled scrollbars instead of Radix ScrollArea; don't add CSS-in-JS libraries.
- **Phase 2's first task is a CSP spike:** build the UI kit and homepage, serve them with the production CSP, and run a Playwright test that listens for `securitypolicyviolation` events and console CSP errors on every page; the gate fails on any violation.
- **Fallback if a needed library must inject styles:** a per-response nonce. Nginx generates it (`$request_id`), adds `'nonce-…'` to `style-src`, and injects it into `index.html` through `sub_filter` as `<meta name="csp-nonce">`; the frontend passes it to the library. This is recorded in DECISIONS.md. `'unsafe-inline'` is never added to `script-src`. Adding it to `style-src` is a last resort that needs a DECISIONS.md entry.
- Development mode (Vite's style injection) uses a relaxed development-only CSP; production and the demo environment always use the strict one.
  - `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`, `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`, `X-Frame-Options: DENY` (legacy).
  - API responses with private data: `Cache-Control: no-store`.
- `TrustedHostMiddleware` with `ALLOWED_HOSTS`; reject unknown `Host` (400) to prevent host-header attacks and DNS rebinding.
- CORS: same-origin only (SPA and API share origin through Nginx); if a dev origin is needed, explicit allowlist, `allow_credentials` only for that origin; never `*`.
- Only `GET, POST, PUT, PATCH, DELETE, OPTIONS` allowed; `TRACE` blocked at Nginx.
- Client IP taken from `X-Forwarded-For` only when the immediate peer is in `TRUSTED_PROXY_IPS`.

### 14.4 Authentication and sessions

- **Passwords:** Argon2id (time_cost 3, memory 64 MiB, parallelism 2; parameters stored in hash; rehash on login if parameters change). Minimum 10 characters, maximum 128, zxcvbn score ≥ 3, rejected if in the bundled breached-password list; no composition rules; allow paste and password managers.
- **Registration:** uniform response; email normalized; phone E.164 and unique (one account per phone); `PENDING` until phone OTP and email verified; PENDING users can only access verification endpoints.
- **Phone OTP:** 6 digits from `secrets`, stored hashed (HMAC-SHA256 with server key), 5-minute expiry, 5 attempts, resend after 60 s, max 5 sends/hour per phone and per IP; constant-time compare; console provider only in development.
- **Email tokens:** 32 random bytes, URL-safe, stored hashed, single use, expiry 24 h (verify) / 30 min (reset); reset revokes all sessions.
- **Login:** uniform error message; per-account and per-IP rate limits; progressive delay after 5 failures; account lock 15 min after 10 failures/hour with email notice; generic timing (always hash a dummy password when the user doesn't exist).
- **Sessions:** 256-bit random token in cookie `__Host-ds_session` (HttpOnly, Secure, SameSite=Lax, Path=/, no Domain); server stores SHA-256 of token; each session token is valid for 15 minutes and is **rotated automatically** (new token, old one revoked after a 30-second grace window for in-flight requests) on the first request after it expires, so an active user stays signed in; idle timeout 30 min; absolute lifetime 7 days, after which the user must sign in again; also rotate on login, privilege change and step-up; logout deletes server state; "log out all devices"; session list shows device/IP/last seen; new-device email.
- **Admin 2FA:** TOTP mandatory (setup forced on first login), secret encrypted at rest (AES-GCM, key from HKDF(SECRET_KEY)), ±1 step window, replay blocked via `last_used_step`; 10 single-use recovery codes (Argon2id-hashed); **step-up** (TOTP within last 10 min) required for: settings changes, dispute decisions, user suspension, project cancellation by admin, reputation recalculation, creating admins.
- **Account deletion:** requires password + typed confirmation; anonymizes PII (email → `deleted+<id>@invalid`, phone null, name "Deleted user", profile/portfolio deleted, files deleted) while keeping ledger, reviews and audit records (pseudonymous) for integrity; last admin cannot be deleted.

### 14.5 Authorization

- Single policy module `core/authz.py`: `authorize(user, action, resource) -> None | raises`. Every service method that reads or writes a resource calls it. Policies implement §2.2 exactly, including object ownership (client owns project; membership via `team_members`; bidder owns bid).
- Not-owned resources return **404** (do not leak existence); wrong role returns 403.
- Sealed bids: only the bidder, the project's client and admins can read a bid; developers' bid lists never include others' prices; `/projects/search` never exposes bid counts or prices.
- Response models are role-specific (e.g., `DeveloperPublic`, `DeveloperForClient`, `DeveloperSelf`) so private fields can't leak by accident.
- Mass assignment prevented by explicit input schemas (`extra="forbid"`); server sets owner ids, roles, statuses, money fields.
- An **authorization matrix test** iterates every route in the OpenAPI spec × every role (anonymous, client, other client, developer, other developer, team lead, admin) against fixtures and asserts the expected status; adding a route without a matrix entry fails the test.

### 14.6 CSRF, clickjacking, redirects

- CSRF: double-submit — `GET /auth/csrf` sets `__Host-ds_csrf` (readable, Secure, SameSite=Strict) bound to the session (HMAC(session_csrf_secret, token)); all unsafe methods require header `X-CSRF-Token` matching and a valid `Origin`/`Referer` equal to `PUBLIC_ORIGIN`; SSE and GET never change state.
- Clickjacking: `frame-ancestors 'none'`.
- **Open redirect prevention** (`core/redirects.py`): `return_to` must be a relative path starting with `/`, not `//`, no backslashes, no scheme, and must match a known frontend route pattern; otherwise the role home is used. Notification `link_path` uses the same validator.

### 14.7 Input validation, output encoding, injection

- Pydantic schemas with lengths, ranges, enums, regex for ids/usernames (simple, linear-time patterns only), Unicode normalization (NFC), stripping of control characters; numbers bounded; arrays bounded (e.g., ≤ 50 skills, ≤ 300 milestones, ≤ 1000 dependencies).
- SQL only through SQLAlchemy expressions; raw SQL banned except migrations and reviewed reports (forbidden-pattern scanner).
- No server-side HTML rendering of user content; emails use templates with autoescape; user text in emails is plain.
- CSV exports neutralize formula injection (prefix `'` for cells starting with `= + - @ \t \r`).
- JSON parsing limits (depth ≤ 20, size ≤ 256 KB); reject NaN/Infinity.
- Search uses PostgreSQL full-text with `plainto_tsquery` (no user regex).

### 14.8 Rate limiting and abuse controls

Two layers: Nginx `limit_req` (coarse per-IP: 20 r/s burst 40 for `/api/`, 5 r/s for `/api/v1/auth/`) and app-level Redis limits (sliding window, keyed as shown). Exceeding → 429 with `Retry-After`, logged as a security event; repeated violations raise a platform alert.

| Scope | Limit | Key |
|---|---|---|
| Authenticated API (global) | 120/min | user |
| Unauthenticated API (global) | 60/min | IP |
| Login | 5/min and 20/hour | IP + email |
| Registration | 5/hour | IP |
| OTP send / verify | 1/60 s, 5/hour / 5 attempts per code | phone + IP / code |
| Password reset request | 3/hour | email + IP |
| Email verification resend | 3/hour | user |
| Bid create/edit | 20/hour | user |
| Project create | 10/day | user |
| Formation runs | 10/hour, 1 concurrent per project | client / project |
| Skill test attempts start | 10/hour | user |
| Coding submissions | 10/hour (practice 30/hour) | user |
| Comments / discussion posts | 60/hour | user |
| Reviews | 30/hour | user |
| Disputes | 5/day | user |
| File uploads | 20/hour, 500 MB/day | user |
| GitHub manual sync | 1/10 min | project |
| Data export | 2/day | user |
| SSE connections | 3 concurrent | user |
| Admin endpoints | 300/min | admin |

Other abuse controls: job queue quotas per user; maximum open bids per developer (30); maximum active projects per client (20); maximum pending invitations per developer (10).

### 14.9 Files and uploads

Allowed types by signature (python-magic), not extension: PNG, JPEG, WebP (images; re-encoded with Pillow to strip EXIF/metadata and limit dimensions ≤ 4096 px; decompression-bomb guard `Image.MAX_IMAGE_PIXELS`), PDF (certificates, max 10 MB, never rendered server-side), ZIP not accepted, plain text/markdown ≤ 1 MB. Size ≤ `MAX_UPLOAD_MB`; streamed to disk (never fully in memory); random storage key (UUID), original name kept only as metadata (sanitized); stored outside web root with 0600 permissions; downloads via `GET /files/{id}/download` → authorization → 302 to a signed URL (HMAC, 5-minute expiry) served by Nginx `internal` location with `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox`. Optional ClamAV scan hook (`scan_status`). Path traversal impossible by construction (no user-controlled paths). Orphan uploads cleaned after 24 h.

### 14.10 Application middleware order (FastAPI)

1. Request id (generate or accept from Nginx; echo `X-Request-ID`) → 2. Trusted host → 3. Body size limit → 4. Security headers → 5. Session load (no DB hit if Redis has it) → 6. CSRF (unsafe methods) → 7. Rate limit → 8. Timeout guard (asyncio timeout per route, default 10 s) → 9. Router → 10. Exception handler (maps domain errors; unknown errors → 500 with request id only; logs full trace server-side).

### 14.11 Money and integrity safeguards

Integer paisa; double-entry transactions whose entries sum to zero (deferred constraint trigger); balances updated in the same transaction with `SELECT … FOR UPDATE` on affected balance rows, ordered by account id to avoid deadlocks; `CHECK (balance_paisa >= 0)` for user and escrow accounts; idempotency keys on fund/deposit/release; daily `ledger.verify` job recomputes balances from entries and raises a CRITICAL platform alert on mismatch; ledger and audit tables are append-only (triggers + no UPDATE/DELETE grants). Reviews are immutable after submission (trigger). Settings changes are versioned. Every money or reputation change is audit-logged.

### 14.12 Secrets, logging, privacy, supply chain, containers

- Secrets only via environment/Docker secrets; `.env` gitignored; `.env.example` has placeholders; gitleaks in pre-commit and CI; startup refuses weak secrets in production.
- Structured JSON logs (structlog) with a redaction processor (keys matching `password|token|secret|otp|code|session|authorization|cookie|totp|phone`) and value patterns (session tokens, emails partially masked); never log request bodies of auth/money endpoints.
- Privacy: minimal PII; phone visible only to the user and admins; data export (JSON + files) and deletion (§14.4); retention: sessions 30 days after expiry, OTPs 1 day, idempotency keys 7 days, logs 30 days.
- Supply chain: hashed lock files (`pip-compile --generate-hashes`, `npm ci`), pip-audit and npm audit (fail on high/critical), Trivy image scan (fail on high/critical with fixes available), Dependabot config, Semgrep (OWASP + python + react rules), Bandit, ESLint security plugin.
- Containers: non-root users, read-only root filesystem (tmpfs for /tmp), `no-new-privileges`, drop all capabilities, CPU/memory limits, health checks, no Docker socket mounted anywhere except Judge0's own internal requirements (Judge0 runs on the isolated `sandbox` network with no internet and no route to Postgres/Redis of the app).
- Database: separate roles — `devsync_migrator` (DDL, used only by migrations), `devsync_app` (DML; no DDL; no UPDATE/DELETE on append-only tables), `devsync_readonly` (analytics/backups); `statement_timeout` 5 s for app, 30 s for jobs; `idle_in_transaction_session_timeout` 10 s.
- Code sandbox (Judge0): CPU 2 s, wall 5 s, memory 128 MB, no network, process limit 32, output ≤ 64 KB, source ≤ 64 KB; API token required; results validated before storage; submissions rate-limited.

### 14.13 Security controls by phase (a phase is not done without its row)

| Phase | Controls that must be implemented and tested |
|---|---|
| 0 | Dependabot config and update policy (§14.21); Claude `/security-review` workflow and `docs/security-reviews/` (§14.22); secure config validation; secrets via env; gitleaks/Bandit/Semgrep/pip-audit/npm audit/Trivy wired into the gate; non-root containers; Nginx TLS (dev certs), HTTPS redirect, security headers, body limits, timeouts; forbidden-pattern scanner; layer checker |
| 1 | RLS foundation (§14.15: context setting, helper functions, policies for identity tables, `check_rls.py`); ALTCHA CAPTCHA and honeypots on public forms (§14.16); admin area hidden (§14.17); production debug-off checks (§14.18); Argon2id; registration/OTP/email/login/reset flows; sessions + rotation + timeouts; CSRF; rate limiting framework + auth limits; lockout; uniform errors; audit log (hash chain); admin TOTP + recovery + step-up; authz module skeleton + matrix test harness; redirect validator; log redaction |
| 2 | CSP-compatible frontend build (no inline); fetch wrapper (CSRF, 401/403/429 handling); route guards; no dangerous DOM sinks; accessibility checks |
| 3 | RLS policies for profile, file and test tables; upload pipeline (signature check, re-encode, size, signed URLs); profile field validation; test timer server-side; answers never exposed; attempt limits |
| 4 | RLS policies for project tables; project/milestone validation bounds; plan size limits; ownership authz; cancellation rules |
| 5 | RLS policies for bids and reservations (sealed bids enforced in the database too); sealed-bid authorization; marketplace never leaks bids; bid limits; availability checks; search input safety |
| 6 | Reputation inputs only from server-side evidence; settings validation; pure algorithm tests |
| 7 | Formation run quotas + idempotency + timeouts; candidate snapshot immutability; explanations visible only to the bidder |
| 8 | Invitation authorization; lead permissions scoped per project; repair authorization |
| 9 | RLS policies for workspace tables; comment/discussion text handling, mention validation, file authz in workspace, SSE auth + Origin + limits, activity events append-only |
| 10 | RLS policies for money tables and the `post_transaction()` function; ledger invariants, row locks, idempotency, append-only triggers, auto-approval correctness, money property tests |
| 11 | RLS policies for reviews (visibility-aware); review immutability, blind visibility rules, integrity rules, contest authorization, trust weighting |
| 12 | RLS policies for disputes, flags, alerts and settings; admin step-up for sensitive actions, dispute decision audit, settings versioning, audit viewer + chain verify, data export/deletion |
| 13 | Webhook verifier `core/webhooks.py` and the optional GitHub webhook (§14.23); GitHub token handling (read-only, env only, no user-supplied URLs fetched), Judge0 isolation + limits, SSRF tests, email header injection tests |
| 14 | Private bucket policy check if object storage is used (§14.19); ZAP baseline clean (no high/medium), schemathesis fuzzing clean, load + chaos tests, rate limits under load, final OWASP Top 10 checklist |
| 15 | Production config validation, backup encryption and restore drill, security documentation complete |

### 14.14 Residual risks (copy into `docs/SECURITY.md`)

Simulated payments only; determined collusion with many real identities can evade rules (mitigated, not prevented); self-hosted TLS certificates in development; Judge0 sandbox strength depends on Judge0's isolation; SMS is simulated in development; no third-party penetration test.

### 14.15 Database row-level security (defence in depth)

Application authorization (§14.5) is the first gate; **PostgreSQL Row-Level Security (RLS)** is the second, so even a forgotten check or a buggy query cannot return another user's private rows.

- **Request context:** at the start of every database transaction the session dependency runs `SELECT set_config('app.user_id', :uid, true), set_config('app.role', :role, true)` (transaction-local, so it is safe with PgBouncer transaction pooling). Anonymous requests set `app.role = 'GUEST'` and no user id. Background jobs use a separate DB role `devsync_worker` and set `app.role = 'SYSTEM'`, plus the id of the user they act for when there is one.
- **Helper SQL functions** (created by migration, `STABLE`, `search_path` pinned, `SECURITY DEFINER` only where needed): `app_uid()`, `app_role()`, `is_admin()`, `is_project_client(project_id)`, `is_project_member(project_id)`, `is_participant(project_id)`.
- **Ownership:** tables are owned by `devsync_migrator`; `devsync_app` and `devsync_worker` are not owners and have no `BYPASSRLS`; every protected table has `ENABLE ROW LEVEL SECURITY` **and** `FORCE ROW LEVEL SECURITY`.
- **Fail closed:** if `app.user_id` is missing, user-scoped policies match nothing.
- **Policies (minimum set; add policies for each new table in the phase that creates it):**

| Table(s) | SELECT allowed when | INSERT/UPDATE allowed when |
|---|---|---|
| `users`, `developer_profiles`, `client_profiles` | own row, admin, or public fields through the `public_profiles` view | own row (the service still restricts columns) |
| `sessions`, `otp_codes`, `email_tokens`, `totp_credentials`, `recovery_codes`, `devices_seen`, `idempotency_keys` | own rows only (SYSTEM for cleanup jobs) | own rows / SYSTEM |
| `projects`, `project_slots`, `milestones`, `milestone_dependencies` | status ≠ DRAFT (any role, GUEST through the `public_projects` view with limited columns), or client of the project, or admin | client of the project |
| `bids`, `bid_explanations`, `availability_reservations` | bidder, client of the project, admin (never other developers: sealed bids) | bidder, while bidding is open |
| `tasks`, `task_dependencies`, `task_evidence`, `comments`, `checkins`, `discussion_threads`, `discussion_posts`, `files`, `activity_events`, `risks`, `forecast_snapshots`, `github_stats` | project participant (client or member) or admin | project member (comments and discussion also the client); SYSTEM for events, risks and snapshots |
| `accounts`, `account_balances`, `ledger_transactions`, `ledger_entries`, `escrows`, `payouts`, `contribution_splits` | account owner; client and members for project-scoped rows; admin | only through `post_transaction()`, a `SECURITY DEFINER` function that enforces the ledger rules; splits by the lead and members per §8 |
| `reviews`, `milestone_ratings`, `review_contests` | reviewer always; reviewee and other participants only when `visibility = 'VISIBLE'`; admin | reviewer, once, during the review window |
| `disputes`, `dispute_statements`, `dispute_evidence` | the parties and admins | parties (statements), SYSTEM (evidence), admin (decision) |
| `notifications`, `notification_preferences` | own rows | SYSTEM / own preferences |
| `test_attempts`, `coding_attempts`, `skill_evidence`, `certificates`, `external_reviews`, `portfolio_items`, `portfolio_images` | owner and admin; verified evidence also through the public profile view | owner; admin for verification |
| `reputation_snapshots`, `reputation_log` | snapshots: any authenticated user (public view); log: the developer and admins | SYSTEM only |
| `integrity_flags`, `platform_alerts`, `audit_log`, `platform_settings` | admin only (settings also readable by SYSTEM) | SYSTEM / admin; the audit log stays append-only |

- **Exempt tables** (no private data, e.g. `skills`) are listed in `backend/app/db/rls_exempt.yml` with a reason. A gate check (`scripts/check_rls.py`) fails if any table is neither RLS-protected nor listed there.
- **Tests:** for each protected table, connect as `devsync_app` with another user's context and assert zero rows or denied writes even when the service-level check is bypassed (calling the repository directly); GUEST sees only the public views; web requests can never set the SYSTEM context.

### 14.16 CAPTCHA and bot protection on public forms

DevSync uses **ALTCHA**, an open-source, self-hosted proof-of-work CAPTCHA: no third-party requests (so it works with the strict CSP and in offline demos) and no image puzzles (accessible).
- **Server:** `GET /api/v1/captcha/challenge` issues a signed challenge (HMAC with `CAPTCHA_HMAC_KEY`, expires in 5 minutes, difficulty from settings). The protected endpoint verifies the solution and signature and stores the challenge id in Redis, so each solution works **once**.
- **Protected forms:** registration, forgot password, email-verification resend, OTP resend, and **login after 3 failed attempts** for the same account or IP (adaptive). Admin login always requires it.
- **Extra layers:** a hidden honeypot field on public forms (if filled, the request is rejected with a generic response), a minimum fill time (under 2 seconds is rejected), and the rate limits in §14.8.
- **Tests:** missing, expired, replayed, tampered or wrong solutions get a generic error; the widget works with the keyboard. In the `test` environment difficulty is minimal; a bypass exists **only** when `DEVSYNC_ENV=test`, and startup fails if it is enabled anywhere else.

### 14.17 Admin area hidden properly

- Every `/api/v1/admin/*` route requires role `ADMIN`, a TOTP-verified session and, for sensitive actions, step-up. Non-admins receive **404**, not 403, so the area isn't confirmed to exist.
- The admin UI is a **separate code-split bundle**, loaded only after `/me` confirms an admin session with verified TOTP. Non-admin users never download admin JavaScript (an E2E test inspects network requests to prove it). No admin links render for other roles; admin routes are excluded from any sitemap and carry `noindex`.
- Optional network restriction: `ADMIN_ALLOWED_CIDRS` (empty means allow all), applied by Nginx to `/admin` and `/api/v1/admin`.
- Admin sessions have a 15-minute idle timeout, and every admin action is audit-logged (§14.11).

### 14.18 Debug features off in production

With `DEVSYNC_ENV=production`, startup **refuses to run** unless all of the following hold, and a CI job boots the app with a production-like environment to prove it: FastAPI `debug=False`; `/docs`, `/redoc` and the public OpenAPI file disabled (OpenAPI for admins only); the `/__test__` router and the CAPTCHA bypass absent; no auto-reload; generic error pages only; console SMS and Mailpit disabled; `/metrics` and `/health/ready` reachable only from the internal network; a production frontend build (React production mode, `console.*` stripped, **no public source maps**: built with `sourcemap: "hidden"` and never served); the `/dev/ui-kit` route excluded from the build; verbose SQL logging off.

### 14.19 Private storage

Files are stored privately and never served directly. Locally and in the demo environment, uploads live on a private volume outside the web root (§14.9). If S3-compatible object storage (for example MinIO) is used in production: the uploads bucket is **private with all public access blocked**, with server-side encryption, versioning and a lifecycle rule for orphaned objects; clients never get upload URLs (every upload goes through the API, so it is validated); downloads use **pre-signed GET URLs valid for 5 minutes** with `Content-Disposition: attachment`; backups go to a separate private, encrypted bucket with different credentials. A gate check confirms the bucket policy denies anonymous access.

### 14.20 Never trust the frontend

Client-side validation and hidden buttons exist only for usability. The server always: takes the user id and role from the session, never from the request; sets owner ids, statuses, timestamps and computed fields itself; **recomputes all money** (escrow = milestone share × budget, fees, splits, payouts) from database values and ignores amounts sent by the client, except values the user legitimately chooses (bid price, deposit), which are checked against bounds; validates every state transition (§8); re-checks file types, sizes and limits; enforces the skill-test timer; bounds every algorithm parameter (weights, thresholds, team size, PSO settings) and page size; whitelists sort and filter fields; and authorizes every id it receives. Each module's tests include "malicious client" cases that send forged ids, amounts, roles and states straight to the API.

### 14.21 Dependency updates

Dependabot runs weekly for pip, npm, Docker base images and GitHub Actions. Policy: critical vulnerabilities fixed within 48 hours, high within 7 days (the gate already fails on unfixed high or critical issues that have fixes). Base images are pinned by digest. `make deps-update` (monthly and before each demo) upgrades within the allowed ranges and runs the full gate. Each release ships an SBOM (`syft`) with the audit results.

### 14.22 Claude security review

At the end of every phase, **before** the gate, Claude Code runs its built-in `/security-review` command on the phase's changes, saves the report to `docs/security-reviews/phase-NN.md`, and fixes every high and medium finding (or records why it is a false positive). The tester then reviews that file as a human second check. Optionally, the same review runs on pull requests through Anthropic's Claude Code security-review GitHub Action (it needs an API key stored as a repository secret). The gate fails if the phase's review file is missing or lists unresolved high findings.

### 14.23 Webhook signatures

DevSync has **no inbound webhooks by default**: GitHub data is pulled and Judge0 results are polled. Any webhook endpoint added later must use `core/webhooks.py`, which reads the **raw** body; verifies an HMAC-SHA256 signature with a per-provider secret using `hmac.compare_digest`; rejects a missing or invalid signature, an unknown event type, a body over 1 MB, or (for providers that sign timestamps) a timestamp older than 5 minutes; stores each delivery id for 7 days and ignores repeats; and answers quickly while the work runs in a background job. The only planned webhook is an optional GitHub push webhook in Phase 13 (*stretch*), verified with `X-Hub-Signature-256` and de-duplicated with `X-GitHub-Delivery`. Webhook routes skip CSRF and session auth but are rate-limited. Tests cover valid, missing, wrong, replayed and oversized deliveries.

### 14.24 Security checklist coverage (quick reference)

| Measure | Where it is specified |
|---|---|
| Row-level security | §14.15 |
| Auth on every API route | §14.5 (deny by default); §16.4 authorization matrix, which fails if any route lacks an entry |
| Never trust the frontend | §14.20 |
| Rate limiting | §14.8 (Nginx and Redis, per action) |
| Sanitize user input | §14.7 (schemas, normalization, plain-text rendering, CSV injection) |
| Parameterized queries | §14.7 (SQLAlchemy bound parameters only; raw SQL banned by §16.7) |
| Lock down CORS | §14.3 (same origin; explicit allowlist only in development) |
| HTTPS everywhere | §14.3 (TLS, redirect, HSTS, `Secure` cookies); §17.0 (trusted local certificate for demos) |
| Stop IDOR bugs | §14.5 (404 for foreign objects); §14.15 (RLS); §16.4 IDOR tests |
| Debug mode off in production | §14.18 |
| CAPTCHA on public forms | §14.16 |
| Log admin actions | §14.11 and §7.1 (hash-chained, append-only audit log) |
| Private storage buckets | §14.19, §14.9 |
| Hide admin pages properly | §14.17 |
| Update vulnerable packages | §14.21; §16.5 step 7 |
| Check file upload types | §14.9 (signature sniffing, re-encoding, size limits) |
| Claude security review | §14.22 |
| Security headers | §14.3 (CSP, HSTS, nosniff, frame-ancestors, referrer, permissions, COOP/CORP) |
| Verify webhook signatures | §14.23 |

---

## 15. Performance, reliability and scalability

### 15.1 Caching

| Layer | What | Policy |
|---|---|---|
| Nginx | Hashed static assets (`/assets/*`) | `Cache-Control: public, max-age=31536000, immutable`; `index.html` `no-cache`; gzip + brotli for text assets |
| Redis cache-aside (`core/cache.py`) | Public project cards, public stats, skills taxonomy, reputation snapshots (public view), recommended projects, CPM results per plan version | Versioned keys (`v{n}:entity:id`), TTL 30 s–10 min, explicit invalidation on writes (service emits `invalidate(keys)` after commit), stampede protection (single-flight lock) |
| HTTP | Public GET endpoints | `ETag` + `If-None-Match` → 304; private endpoints `no-store` |
| TanStack Query | Client-side | `staleTime` per resource (§13.7); background refetch on focus for dashboards |
| DB | Hot queries | Indexes (§7.9), `selectinload` to avoid N+1 (tests assert query counts on key endpoints) |

### 15.2 Load balancing and scaling

Nginx upstream `api` with `least_conn` over N API replicas (`docker compose --scale api=3`), passive health checks (`max_fails=3 fail_timeout=10s`), keep-alive to upstreams; SSE routed to the same pool (stateless; Redis pub/sub fan-out for notifications). RQ workers scale independently (`worker` replicas with queue priorities: `high` (formation, auth emails), `default`, `low` (sync, analytics)). PgBouncer in transaction pooling mode in production. Everything stateful lives in Postgres/Redis, so replicas can be added or removed without sticky sessions.

### 15.3 Timeouts (every layer)

| Layer | Timeout |
|---|---|
| Nginx | `client_header_timeout 10s`, `client_body_timeout 15s`, `send_timeout 15s`, `keepalive_timeout 30s`, `proxy_connect_timeout 3s`, `proxy_read_timeout 30s` (SSE location 35 min with heartbeats), `client_max_body_size 1m` (25m on upload location) |
| Gunicorn/Uvicorn | worker `timeout 30`, `graceful_timeout 20`, `keepalive 5`, `max_requests 1000` + jitter 100 |
| App route guard | 10 s default (most endpoints finish < 300 ms) |
| PostgreSQL | `statement_timeout` 5 s (app) / 30 s (jobs), `lock_timeout` 3 s, `idle_in_transaction_session_timeout` 10 s |
| Redis | socket connect 1 s, socket timeout 1 s, retry once |
| httpx (GitHub, Judge0, SMTP) | connect 3 s, read 10 s, total 15 s; retries with exponential backoff + jitter; circuit breaker (open after 5 failures for 60 s) |
| RQ jobs | per-job `job_timeout` (§11); `result_ttl` 1 day |
| Frontend | fetch abort after 15 s (GET retry ×2 with backoff), job polling stops after job timeout |

### 15.4 Memory and resource bounds

Container limits (prod): api 512 MB each, worker 768 MB, scheduler 128 MB, nginx 128 MB, redis 256 MB with `maxmemory-policy allkeys-lru` for the cache DB and a separate DB index (no eviction) for sessions/queues (`noeviction` instance in production), postgres 1 GB. Algorithms bounded: shortlist ≤ 200 candidates, team size ≤ 10, PSO particles ≤ 50, iterations ≤ 400, exact solver guarded by combination count. Uploads streamed. Pagination caps. Large exports are jobs writing files, not responses. Gunicorn `max_requests` recycles workers; RQ workers restart after 500 jobs.

### 15.5 Redirects and routing

HTTP → HTTPS (301); `www.` → apex (301) in production; trailing-slash normalization for API (no trailing slash; 308 to canonical); SPA fallback: unknown non-API paths serve `index.html` (client router shows 404); post-login redirect by role or validated `return_to` (§14.6); post-logout to `/login`; email links (verify, reset) land on SPA routes that call the API, then redirect to the role home; legacy/renamed routes get explicit redirects in the router.

### 15.6 Reliability

Health: `/health` (liveness, no dependencies) and `/health/ready` (DB, Redis, queue reachable; internal only). Graceful shutdown: stop accepting, finish in-flight requests (20 s), workers finish current job or re-queue. Transactional outbox for emails (no lost or duplicate sends). All jobs idempotent and retry-safe. Backups: nightly `pg_dump` (encrypted with age/GPG key from env), 7 daily + 4 weekly retained, restore drill script `make restore-drill` (restores into a temp DB and runs smoke checks). Database migrations are backwards-compatible (expand → migrate → contract) and tested up/down in the gate.

### 15.7 Observability

JSON logs with `request_id`, `user_id` (hashed in logs), route, status, duration; metrics endpoint `/metrics` (internal network only): request latency histograms, error rates, job durations/failures, queue depth, cache hit ratio, DB pool usage, rate-limit rejections; slow query log (> 500 ms); frontend error boundary reports to `/api/v1/client-errors` (rate-limited, sanitized).

---

## 16. Testing strategy and the phase gate

### 16.1 Test layers

| Layer | Tool | Location | Marker | Purpose |
|---|---|---|---|---|
| **Backend unit** (supervisor requirement) | pytest | `backend/tests/unit` | `unit` | **Every** service function, validator, helper, state transition and permission rule, tested in isolation with fakes for the DB and integrations; written in the same commit as the code; test names reference FR-IDs |
| Algorithm | pytest + hypothesis | `backend/tests/algorithms`, `property` | `property` | Every equation (hand-computed examples from the paper's definitions), invariants, PSO vs exact |
| Integration | pytest + testcontainers (Postgres 16, Redis 7) | `backend/tests/integration` | `integration` | Repositories, transactions, triggers, migrations, jobs |
| API | httpx AsyncClient against the app | `backend/tests/api` | `api` | Every endpoint: success, validation, authz, state errors |
| Contract fuzzing | schemathesis on OpenAPI | `backend/tests/api/test_schemathesis.py` | `fuzz` | No 500s, schema-conformant responses, stateful links |
| Security | pytest | `backend/tests/security` | `security` | Every control in §14 (list in §16.4) |
| Jobs | pytest with RQ `SimpleWorker` | `backend/tests/jobs` | `jobs` | Idempotency, retries, timeouts |
| **Frontend unit/component** (supervisor requirement) | Vitest + RTL + MSW | `frontend/tests` | — | **Every** component, hook, form schema, formatter and route guard |
| Accessibility | @axe-core/react (unit) + @axe-core/playwright (E2E) | both | `a11y` | Zero serious/critical violations |
| End-to-end | Playwright (Chromium, Firefox, WebKit; mobile viewport) | `e2e/` | `@e2e` | Real browser flows across roles |
| Visual regression | Playwright screenshots | `e2e/visual` | `@visual` | Key screens light/dark at 1440 and 390 widths; threshold 0.2% |
| Performance | pytest perf + k6 | `backend/tests/perf`, `infra/k6` | `perf` | Algorithm budgets; API latency/throughput thresholds |
| Chaos/resilience | scripted (compose kill/restart) | `e2e/chaos` | `chaos` | Worker crash, Redis restart, DB restart, upstream timeout |
| DAST | OWASP ZAP baseline (+ API scan with OpenAPI) | CI | — | No high/medium alerts |
| Static/supply chain | ruff, mypy, ESLint, tsc, Bandit, Semgrep, gitleaks, pip-audit, npm audit, Trivy | gate | — | Clean |

**Unit testing rule:** no backlog item is done without unit tests. The gate reports unit test counts per module and fails if a new module in `app/services`, `app/core`, `app/algorithms` or `frontend/src/features` has no unit test file. `docs/TESTING.md` contains a unit-test summary table (module → number of tests → coverage) refreshed at every gate, for the supervisor.

### 16.2 Test data and determinism

Factories (factory-boy) for every model; `freezegun`/injectable clock for time-dependent rules; seeded RNG for algorithms and the simulator; Playwright fixtures create users per role via a **test-only** API (`/__test__/seed`, mounted only when `DEVSYNC_ENV=test`, guarded by a startup check that fails in production) and log in through the real UI once per role (storage state reused).

### 16.3 Core fixtures (`backend/tests/conftest.py`)

`db` (transaction rollback per test), `redis` (flushed), `client(role)` authenticated AsyncClient with CSRF token, `users` (client, other_client, developer, other_developer, newcomer, lead, admin with TOTP), `project_factory(state=…)` builds projects in any state machine state, `team_factory`, `ledger_funded_project`, `frozen_clock`, `rq_worker` (synchronous), `settings_override`.

### 16.4 Mandatory security test list (grows by phase; never deleted)

- **Authz matrix:** every route × every role and ownership case (anonymous 401, wrong role 403, foreign object 404, correct 2xx); fails if a route lacks an entry.
- **IDOR:** for every resource with an id in the path, access with another user's id returns 404.
- **Mass assignment:** posting extra fields (`role`, `status`, `owner_id`, `balance_paisa`, `is_lead`) → 422.
- **CSRF:** unsafe requests without token/with wrong token/with foreign Origin → 403; GET never mutates (test by checksumming DB before/after GETs).
- **Sessions:** fixation (token changes after login), idle/absolute expiry, logout invalidates, logout-all, cookie flags (`HttpOnly`, `Secure`, `SameSite`, `__Host-`).
- **Auth:** uniform errors (no enumeration; timing difference < 50 ms over 50 samples), lockout and unlock, OTP expiry/attempts/resend, reset token single-use and expiry, password policy, breached passwords, admin TOTP replay and window, recovery codes single-use, step-up enforcement.
- **Rate limits:** every row of §14.8 returns 429 at the limit with `Retry-After` and resets.
- **Headers:** CSP exact value, HSTS, nosniff, frame-ancestors, referrer, permissions policy, no `Server` version leak.
- **Injection corpus:** SQLi/XSS/template/command payloads in every text field (search, comments, profile, project text, filenames) are stored/returned inert; search with special characters doesn't 500.
- **Uploads:** wrong signature, polyglot files, oversized, decompression bomb, EXIF stripped, path-like names, signed URL expiry and tampering.
- **Redirects:** `return_to` values `//evil.com`, `https://evil.com`, `/\evil.com`, `javascript:` → role home.
- **SSRF:** GitHub repo URLs pointing to internal hosts/IPs are rejected; only `https://github.com/<owner>/<repo>` accepted and only the API host is called.
- **Sealed bids:** developers can never retrieve others' bids by any endpoint; search responses contain no bid data.
- **Money:** concurrent double-fund/double-approve → exactly one succeeds; ledger always balances (property test over random operation sequences); negative balances impossible; idempotent replays return the same response.
- **Append-only:** UPDATE/DELETE on audit, ledger, activity events and review content fail at the DB level.
- **Audit chain:** tampering with a row is detected by `/admin/audit/verify`.
- **Error handling:** forced exceptions return the generic 500 body with request id, no stack trace.
- **Host header / methods:** bad Host → 400; TRACE blocked.
- **SSE:** requires session, rejects foreign Origin, enforces concurrent limit.
- **Row-level security:** for every protected table, cross-user reads and writes through the repository layer (bypassing service checks) return nothing or fail; `check_rls.py` passes.
- **CAPTCHA:** missing, expired, replayed or tampered solutions are rejected on every protected form; the adaptive login CAPTCHA appears after 3 failures; honeypot submissions are rejected.
- **Admin hiding:** non-admins get 404 from every admin API route, and the admin JavaScript bundle is never requested by non-admin sessions.
- **Production mode:** booting with `DEVSYNC_ENV=production` and any debug feature on fails; docs, the test router and source maps are not reachable.
- **Malicious client:** forged amounts, ids, roles, states and over-limit parameters sent directly to the API are rejected or ignored.
- **Webhooks (if enabled):** a valid delivery is accepted once; missing, wrong, replayed and oversized deliveries are rejected.
- **Sandbox:** Judge0 submissions with infinite loops, fork bombs, network access attempts, huge outputs → bounded failures, no impact on API.

### 16.5 The phase gate (`make gate PHASE=N` → `backend/scripts/phase_gate.py`)

Runs in order; stops at first failure unless `--keep-going`; always prints a summary table (step, status, duration, notes), writes `runs/gates/phase-N.json`, appends to `PROGRESS.md`, and prints `PHASE N GATE: PASS` or `PHASE N GATE: FAIL (step X)`.

1. **Environment:** tool versions; Docker running; no untracked secret-like files.
2. **Build:** `docker compose -f docker-compose.yml -f docker-compose.test.yml build`; frontend `npm ci && npm run build` (with bundle-size budget check §13.7).
3. **Format & lint:** `ruff format --check`, `ruff check` (rules `E,F,W,I,B,UP,S,SIM,C4,RUF,ASYNC,PL,PT,N`), `eslint --max-warnings 0`, `prettier --check`.
4. **Types:** `mypy` (strict for `app/core`, `app/algorithms`, `app/services/money*`, `app/services/auth*`; `disallow_untyped_defs` everywhere), `tsc --noEmit` (strict).
5. **Static security:** Bandit (fail on medium/high), Semgrep (`p/owasp-top-ten p/python p/react p/secrets` + `infra/semgrep/devsync.yml` custom rules), gitleaks.
6. **Forbidden patterns:** `scripts/check_forbidden.py` (§16.7). **Layer rules:** `scripts/check_layers.py`. **RLS coverage:** `scripts/check_rls.py` (§14.15). **Security review:** `docs/security-reviews/phase-N.md` exists and has no unresolved high findings (§14.22).
7. **Dependency audit:** pip-audit, `npm audit --audit-level=high`, Trivy on built images (high/critical with fixes → fail). `--offline` skips with a recorded note.
8. **Migrations:** upgrade to head on an empty DB, downgrade one step and upgrade again; check model/migration drift (`alembic check`).
9. **Backend tests:** `pytest -m "not perf and not chaos" --cov=app --cov-branch` with phase coverage threshold; per-module ≥ 95% for security-critical modules (`core/security.py`, `core/sessions.py`, `core/csrf.py`, `core/authz.py`, `core/ratelimit.py`, `core/redirects.py`, `core/money.py`, `services/ledger*.py`, `uploads/*`) from the phase they appear; algorithms ≥ 95%.
10. **Security suite:** `pytest -m security` (must be non-empty from Phase 1).
11. **API contract:** `scripts/check_openapi.py` (§10.4) passes and `docs/api/openapi.json` matches the code. **API fuzzing:** schemathesis (from Phase 1; 200 examples per operation; stateful from Phase 5): zero 500s, zero schema violations.
12. **Frontend tests:** `vitest run --coverage` (threshold by phase) including axe checks.
13. **E2E:** `docker compose up -d` test stack; Playwright `@e2e` on Chromium (all phases ≥ 2), plus Firefox and WebKit at the demo phases 5, 12, 15; responsive viewport matrix and mobile touch flows from §13.14 on every built screen; repeated ×3 at the demo phases to catch flakiness; traces/screenshots on failure.
14. **Accessibility:** Playwright axe scan on every screen built so far (0 serious/critical).
15. **Visual regression** (from Phase 2): screenshots of built screens (light/dark, desktop/mobile); diffs fail unless baselines are intentionally updated with `make visual-update` and noted in PROGRESS.md.
16. **Performance** (from Phase 4): algorithm budgets (CPM 300 milestones < 50 ms; PSO |S|=200 < 5 s; exact solver 18 candidates < 3 s; reputation update for 50-project history < 20 ms); from Phase 14 also k6 (§16.8).
17. **DAST** (from Phase 9; full at 14–15): ZAP baseline against the running stack with an authenticated context; no high/medium.
18. **Phase-specific checks** (`PHASE_CHECKS[N]`, listed under each phase in §17).
19. **Regression guard:** compare test counts with `runs/gates/baseline.json` — tests may be added, never removed or newly skipped without a DECISIONS.md entry.
20. **Report** and write `.phase` on PASS.

**Coverage thresholds (backend / frontend):** phases 0–3: 75% / 60%; 4–9: 85% / 70%; 10–15: 90% / 75% (branch coverage on).

### 16.6 Makefile targets (required)

`make env` (generate `.env` with strong secrets), `make certs`, `make up` / `make down` / `make logs`, `make migrate`, `make seed-demo`, `make create-admin`, `make test` (backend+frontend fast), `make test-unit` (backend + frontend unit tests only, fast), `make test-backend`, `make test-frontend`, `make e2e`, `make a11y`, `make visual` / `make visual-update`, `make security` (static + security tests), `make fuzz`, `make zap`, `make load`, `make chaos`, `make gate PHASE=N`, `make demo-check DEMO=N`, `make seed-demo STAGE=N`, `make demo-up STAGE=N`, `make demo-reset STAGE=N`, `make demo-preflight`, `make erd`, `make experiments`, `make backup` / `make restore-drill`, `make docs`.

### 16.7 Forbidden-pattern scanner (`scripts/check_forbidden.py`)

Fail on (outside tests unless stated):
- Python: `eval(`, `exec(`, `pickle`, `marshal`, `shelve`, `yaml.load(` (only `safe_load`), `subprocess` with `shell=True`, `os.system`, `os.popen`, `tempfile.mktemp`, `random.` in security modules (use `secrets`), `==`/`!=` on names matching `token|secret|digest|hash|otp|signature|csrf` (use `hmac.compare_digest`), `text(` raw SQL outside `alembic/` and `app/reports/`, `float(` or `/ 100` on names ending `_paisa`, any `float` or `math.` call inside `app/core/money.py`, `app/algorithms/payment_policy.py`, `app/algorithms/splits.py` or `app/services/ledger*.py` (use `Decimal`), `print(` in `app/`, `assert` in `app/`, logging of variables named `password|token|secret|otp|session`, `verify=False` in httpx, `allow_origins=["*"]`, `TODO|FIXME` in security-critical modules.
- TypeScript/JS: `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval(`, `new Function(`, string `setTimeout(`, `localStorage`/`sessionStorage` for tokens or PII (UI preferences allowed via an allowlisted helper), `http://` or `https://` literals to external origins (except `github.com` display links and docs), `target="_blank"` without `rel="noopener noreferrer"`.
- Repository: private keys, `.env` files, tokens (gitleaks rules), committed uploads.
Exceptions require `# forbidden-ok: <reason>` / `// forbidden-ok: <reason>` on the same line and are listed in the gate report.

### 16.8 Load and chaos tests (Phase 14)

k6 scenarios against the production-like compose (`api` ×3, `worker` ×2): browse/search (60% traffic), dashboards (20%), task moves/comments (15%), bids (5%) with 200 virtual users for 10 minutes. Thresholds: p95 < 400 ms, p99 < 1 s for normal endpoints, error rate < 0.5%, no 5xx except intentional 429s; formation run p95 < 8 s end-to-end under load. Spike test (0 → 400 VUs in 30 s): no crash, recovers within 60 s. Soak (30 minutes, 100 VUs): API RSS growth < 100 MB, no connection pool exhaustion. Chaos: kill one API replica during load (errors < 1%, LB routes around), restart Redis (sessions survive via DB fallback; rate limits fail closed for auth endpoints, open for reads), kill a worker mid-PSO (job retried or reported failed; no duplicated team), DB restart (requests fail fast with 503 and recover).

### 16.9 CI (`.github/workflows/ci.yml`)

On push/PR: build images with cache, run `make gate PHASE=$(cat .phase)` in the test compose; upload gate report, coverage, Playwright traces/screenshots, ZAP report as artifacts; nightly workflow runs the full gate including all browsers, visual tests, ZAP full baseline and a short k6 smoke. Pre-commit: ruff, ruff-format, prettier, eslint (changed files), gitleaks, check_forbidden.

### 16.10 When the gate fails

Fix the cause; never weaken a test, threshold, lint rule or security default to pass. If a test is genuinely wrong, fix it and record why in DECISIONS.md. Flaky tests are bugs (find the race; don't add blind retries). Report the final gate table to the student at the end of each phase.

---

## 17. Build phases

Every phase lists: **Goal · Read first · Build (backend, frontend) · Security · Tests · Gate checks · Manual check · Acceptance.** Priorities: everything listed in a phase is required unless marked *(stretch)*. Demo phases (extra E2E browsers, ×3 repetition, demo readiness check §17.0): 5, 12, 15.

### 17.0 Demo schedule and phase grouping (read before planning any phase)

The course has **three graded demos**. Dates (record changes in `PROGRESS.md`): **Demo 1 — Mon 2 Nov 2026**, **Demo 2 — Mon 7 Dec 2026**, **Demo 3 — Mon 4 Jan 2027**. Work starts **Mon 12 Oct 2026**. Demos 1 and 2 carry most of the features, **Demo 2 slightly more than Demo 1**, and Demo 3 the fewest.

| Demo | Phases | Build window | Share of phase work | What must work at the demo |
|---|---|---|---|---|
| **Demo 1 — Core platform & planning** (2 Nov) | 0–5 | 12 Oct – 1 Nov (3 weeks) | ≈ 36% | Accounts & security core (verification, sessions, admin 2FA, rate limits, audit log); design system & landing page; profiles, portfolio & timed skill tests; project wizard with the **CPM timeline** (Gantt, critical path); marketplace with search, **sealed bids** and **Algorithm 1 filtering** (eligibility reasons, newcomer rule, too-few-bids handling) |
| **Demo 2 — Research engine & full lifecycle** (7 Dec) | 6–12 | 2 Nov – 6 Dec (5 weeks) | ≈ 47% | **[PCS] reputation engine** + simulator; **team formation** (BPSO, exact verification, fairness dial, cost of fairness, "why this team", comparison, "why not selected"); invitations, **team lead selection (§1.6)**, team repair; workspace, **client progress watching**, risk dashboard; milestones, escrow, **[PCS] payment policy**, auto-approval; blind reviews, integrity, reputation update, post-mortem; disputes and the admin console |
| **Demo 3 — Proof & polish** (4 Jan) | 13–15 | 7 Dec – 3 Jan (4 weeks, including the holiday period; lightest workload) | ≈ 17% | GitHub evidence and coding challenges (the only new features); performance, load balancing, chaos and security results; experiments E1–E9; deployment and final documentation |

Timeline detail (owner in brackets; TL = team leader, BE = backend developer, FE = frontend developer, QA = tester): P0 12–15 Oct (TL+QA) · P1 14–21 Oct (BE) · P2 14–22 Oct (FE) · P3 19–26 Oct (BE+FE) · P4 20–28 Oct (TL+FE) · P5 24–31 Oct (BE+TL) · Demo 1 readiness 30 Oct–1 Nov (QA) · P6 2–9 Nov (TL) · P7 5–15 Nov (TL+FE) · P8 12–18 Nov (BE+TL) · P9 14–24 Nov (FE+BE) · P10 19–28 Nov (BE) · P11 25 Nov–2 Dec (TL+BE) · P12 28 Nov–4 Dec (BE+FE) · Demo 2 readiness 4–6 Dec (QA) · P13 7–14 Dec (BE) · P14 10–23 Dec (QA+BE) · P15 17–30 Dec (TL+QA) · Demo 3 readiness 31 Dec–3 Jan (QA). Phases overlap deliberately: start a phase as soon as its dependencies' APIs and tests are stable, but **the gate of a phase must pass before any later phase's gate**. Testing, security and documentation run continuously.

**Demo readiness check.** After the last phase of each group (5, 12, 15), in addition to the phase gate, run `make demo-check DEMO=N`, which: (1) re-runs the gates of all phases in the group; (2) resets and loads the demo seed for that stage (`make seed-demo STAGE=N`); (3) runs the scripted walkthrough as a Playwright test (`e2e/demos/demo-N.spec.ts`) on Chromium, Firefox, WebKit and a mobile viewport, three times; (4) writes `runs/demos/demo-N.md` with screenshots of every step, the gate table and known limitations. The student uses this report to rehearse.

**Demo walkthroughs (each becomes `e2e/demos/demo-N.spec.ts`):**
- **Demo 1:** landing page → client registers and verifies (OTP, email) → admin logs in with TOTP → client creates a 6-milestone project in the wizard; the CPM timeline shows the critical path and slack; a circular dependency is rejected → developer (newcomer) completes a profile and passes a timed skill test → developers search and filter projects and place sealed bids; one bid shows "would be filtered out because…" → a second developer cannot see the first developer's bid → client sees all bids with eligibility reasons; the too-few-bids banner appears on a project with insufficient bids.
- **Demo 2:** reputation pages of an experienced developer and a newcomer → client runs team formation with the fairness dial at 1 → live convergence chart, "Optimal" verification, cost of fairness, "why this team", team comparison → a non-selected developer reads "why not selected" → invitations accepted, one declined → team repair with ranked candidates → system recommends a lead, client confirms → lead creates tasks, members move them and post check-ins → client watches progress and sees a CRITICAL risk with the deadline impact → milestone submitted, changes requested, resubmitted, approved with 5 stars → payout with reward → a member objects to a split → admin resolves with step-up 2FA → project completes → blind reviews → reputation changes and post-mortem.
- **Demo 3:** link a GitHub repo and sync evidence; solve a coding challenge → run the k6 load test while killing an API replica → show the security report (ZAP, fuzzing, OWASP checklist) → show experiment charts (E1, E3, E4, E7) → full walkthrough on the production-style deployment.

**Demo-day environment.** Presentations run on a team laptop with `make demo-up STAGE=N`: the production-style compose profile (HTTPS with a locally trusted certificate created by `make certs` using mkcert, two API replicas behind Nginx, workers, real security settings) that works **fully offline** (no external calls; GitHub and email use recorded fixtures and Mailpit). `make demo-reset STAGE=N` restores the seed in under 30 seconds between rehearsals. The readiness check also records the walkthrough as a video (`runs/demos/demo-N.webm`, Playwright `video: "on"`) as a fallback if the live demo fails. Demo accounts and their one-time passwords are printed by the seed script and saved to `runs/demos/accounts-N.txt` (gitignored). A pre-flight script (`make demo-preflight`) checks Docker, ports, certificate trust, disk space and seed integrity 30 minutes before presenting.

**What earns marks first.** Demos 1 and 2 carry most of the marks. Within those phases, finish and polish the demo-path screens (the walkthroughs above) before secondary screens; a flawless walkthrough with every state handled beats many half-finished pages. Do a dedicated **polish pass** in the readiness window (30 Oct–1 Nov and 4–6 Dec): visual consistency against §13.8, empty/loading/error states, microcopy (§13.10), dark mode, mobile layout, and performance of the demo paths.

**Pre-demo work:** the student's proposal, use case diagram, ERD (generate `docs/design/erd.svg` from the models in Phase 4 using a script), architecture diagram and Gantt chart are prepared in the first week. Ask the student to confirm all dates during Phase 0; if a phase group is at risk of missing its demo, warn the student at least one week before.

**If a demo is at risk** (decide with the student; record in DECISIONS.md): before Demo 1, skill tests may move to Demo 2 and recommended projects may move to Demo 2 — the CPM planner and sealed bidding with filtering never move. Before Demo 2, team comparison, client analytics, file previews and notification preferences may move to Demo 3 — reputation, BPSO team formation, payments, reviews and disputes never move. In Demo 3, GitHub evidence and coding challenges may be dropped; tests, security results and experiments may not.

### 17.1 Development process: Agile (Scrum-based), one-week sprints

DevSync is built with an **Agile, Scrum-based, iterative and incremental** process. The supervisor and the student team see a working, tested increment every week, and a release at each presentation.

| Scrum element | How it works in DevSync |
|---|---|
| **Product backlog** | Every functional requirement (FR-IDs in the proposal) and every phase task in §17, ordered by the phase plan and priorities (Core → Expected → Stretch). Kept in `docs/BACKLOG.md` (one line per item: id, title, phase, priority, status, owner) |
| **Sprints** | 12 one-week sprints, Monday to Sunday: S1 starts Mon 12 Oct 2026, S12 ends Sun 3 Jan 2027. Sprints S1–S3 deliver Phases 0–5 (presented 2 Nov), S4–S8 deliver Phases 6–12 (presented 7 Dec), S9–S12 deliver Phases 13–15 (presented 4 Jan) |
| **Sprint planning** | At the start of each sprint, Claude Code (in Plan Mode) proposes the sprint goal and the backlog items to finish, based on the phase plan; the student approves. Saved to `docs/sprints/sprint-NN.md` |
| **Daily progress** | Short entries in `PROGRESS.md` (done, next, blockers) instead of meetings |
| **Increment & Definition of Done** | A backlog item is done only when its code, **unit tests**, integration/API tests, security tests for its controls (§14.13) and documentation are complete, and the relevant phase gate passes |
| **Sprint review** | At the end of each sprint: a short demo of what works (`make seed-demo` + the relevant Playwright walkthrough), recorded in `docs/sprints/sprint-NN.md` |
| **Retrospective** | Three lines per sprint in the same file: what went well, what didn't, one change for next sprint |
| **Releases** | Tagged releases at the presentations: `v0.1.0` (2 Nov), `v0.2.0` (7 Dec), `v1.0.0` (4 Jan) |
| **Roles** | Product owner and Scrum master duties: the team leader (with the supervisor as key stakeholder); development team: team leader, backend developer, frontend developer and tester (+ Claude Code as an assistant) |

Phases (§17) remain the technical structure and the phase gate remains mandatory; sprints are the weekly rhythm in which the phases are delivered. When a phase spans two sprints, each sprint still ends with all completed items tested and documented.

---

### Phase 0 — Foundations, tooling, infrastructure

**Goal:** an empty but production-shaped system: containers, Nginx with TLS and headers, database roles, migrations, settings, logging, CI and the phase gate, all green.

**Read first:** §3, §4, §5, §6, §14.3, §14.12, §15.3–15.6, §16.

**Build — backend:**
1. Repository tree (§4) with placeholders; `CLAUDE.md` (≤ 60 lines: rules from §0, commands, pointer to this spec), `PROGRESS.md`, `DECISIONS.md`, docs stubs.
2. `pyproject.toml` (ruff, mypy, pytest markers with `--strict-markers`, coverage, bandit), hashed lock files.
3. `core/config.py` with all env vars (§6.1) and production startup validation; `core/logging.py` (structlog JSON, request id, redaction processor); `core/errors.py` (error codes, safe handler); `core/clock.py`; `db/` (async engine, session dependency, base model with timestamps, naming conventions).
4. Alembic configured to use `MIGRATION_DATABASE_URL`; first migration: `platform_settings`, `audit_log` (with append-only trigger and hash chain function), `jobs`, `idempotency_keys`; seed default settings (§6.2) with validation.
5. `main.py` app factory with middleware order (§14.10), `/health`, `/health/ready`, `/metrics` (internal).
6. RQ worker and scheduler services with a `ping` job; graceful shutdown.
7. `infra/postgres/init` creating roles `devsync_migrator`, `devsync_app`, `devsync_readonly` with least privilege.
8. `infra/nginx/nginx.conf`: TLS (dev certs from `make certs`), 80→443, security headers, `limit_req` zones, body limits, all timeouts (§15.3), gzip/brotli, upstream `api` with `least_conn`, SPA static serving with immutable asset caching, internal file location placeholder, `/metrics` and `/health/ready` blocked externally, TRACE blocked.
9. Compose files (dev/test/prod) with networks (§5.1), health checks, non-root users, read-only fs, resource limits (prod), `no-new-privileges`, dropped capabilities.
10. Scripts: `phase_gate.py` (all steps; steps for not-yet-existing parts run on what exists), `check_forbidden.py`, `check_layers.py`; `.pre-commit-config.yaml`; CI workflow; Makefile targets (§16.6); `.phase` = none.
11. **Skills (§0.4):** with the student, install `frontend-design` (https://github.com/anthropics/skills/tree/main/skills/frontend-design) and the CloudAI-X Three.js skills (https://github.com/CloudAI-X/threejs-skills) into `.claude/skills/`, review every `SKILL.md` and script, record the reviewed commit hashes in `DECISIONS.md`, and commit the folder. Add `.claude/skills/README.md` listing each skill, its source link, commit and purpose.

**Build — frontend:** Vite + React + TS strict; Tailwind with tokens (§13.1) and dark theme variables; fonts self-hosted; ESLint/Prettier; Vitest + RTL + MSW setup; Playwright config (projects: chromium, firefox, webkit, mobile) and a smoke test that loads `/` through Nginx; CSP-compatible build (no inline scripts/styles; verify with a test that parses `dist/index.html`).

**Security:** §14.13 row 0.

**Tests:** config (defaults, overrides, insecure production combos refused); logging redaction (token/password/otp values masked); error handler (no traces); health endpoints; audit append-only trigger and hash chain; settings validation (invalid weight sums rejected); Nginx: HTTPS redirect, security headers present and exact CSP, TRACE → 405/444, oversize body → 413, `/metrics` not reachable externally; frontend smoke + contrast test for tokens.

**Gate checks (P0):** compose stack healthy; migrations up/down; `curl -k https://localhost/health` → 200 with headers; scanners clean.

**Manual check:** `make env certs up` → open `https://localhost` (self-signed warning accepted) → placeholder page loads with Inter font, no console errors, no external requests (DevTools network tab).

**Acceptance:** `PHASE 0 GATE: PASS`.

---

### Phase 1 — Accounts, authentication, sessions, security core

**Goal:** complete, hardened identity layer and security framework that all later phases rely on.

**Read first:** §2, §7.1, §8 (User), §10 (Auth, Me), §12, §14.4–14.8, §14.10, §16.4.

**Build — backend:**
1. Models + migration: users, sessions, otp_codes, email_tokens, totp_credentials, recovery_codes, devices_seen, notifications (table only), email_outbox.
2. `core/security.py` (Argon2id with rehash, token generation via `secrets`, HMAC helpers, constant-time compare, AES-GCM helper for TOTP secrets via HKDF), `core/sessions.py` (Redis + DB, rotation, idle/absolute expiry, list/revoke), `core/csrf.py`, `core/ratelimit.py` (sliding window Lua script; per-route decorators; limits from §14.8), `core/authz.py` (policy registry, `authorize()`; roles; ownership hooks used later), `core/redirects.py`, `core/audit.py`, `core/idempotency.py`.
3. Services and endpoints: register (uniform response), OTP send/verify, email verify/resend, login (+ admin TOTP second step), logout, logout-all, sessions list/revoke, password forgot/reset/change, me get/patch, TOTP setup/confirm, recovery codes, step-up; account lockout; new-device email; breached-password list loader (bundled compressed file of SHA-1 prefixes or plain top-100k list).
4. SMS provider interface (`console` dev, `noop` test); email via outbox + Mailpit; email templates (autoescaped, plain text + HTML).
5. `scripts/create_admin.py` (interactive, prints TOTP provisioning URI once).
6. Test-only seed router (`/__test__/seed`) mounted only in `test` env with a startup assertion.

**Build — frontend (screens 2–5 functional; styling refined in Phase 2):** login, admin TOTP step, register (role step), verify (OTP + email), forgot/reset, minimal authenticated placeholder pages per role; fetch wrapper with CSRF, 401/403/429 handling; route guards and role redirects; session-expired handling.

**Security:** §14.13 row 1 (full).

**Tests:** every item in §16.4 that applies to auth/sessions/CSRF/rate limits/redirects/headers/errors; authz matrix harness (with current routes); property tests for token generation uniqueness and redirect validator (hypothesis-generated paths); E2E: register → verify phone (OTP read from test seed endpoint/Mailpit API) → verify email → land on role dashboard; login wrong password ×N → lockout message; admin login with TOTP; logout-all invalidates another browser context.

**Gate checks (P1):** register+verify+login via API script; admin TOTP flow; rate-limit 429 observed on login; audit chain verifies.

**Manual check:** register as client and developer, verify via Mailpit (`http://localhost:8025` in dev), login/logout, see sessions list, admin login requires TOTP.

**Acceptance:** gate PASS; security suite non-empty and green; no route without authz matrix entry.

---

### Phase 2 — Design system, app shell, landing page

**Goal:** the complete visual language, components, motion system, layouts and navigation, so every later screen is fast to build and consistent.

**Read first:** §13 (all), §15.5, §0.4 (skills), §13.11–13.13.

**Build — frontend:**
1. Tokens (`tokens.css`), theme provider (light/dark/system), reduced-motion provider (OS + user setting), motion variants (`design/motion.ts`) implementing the catalogue (§13.2).
2. shadcn/ui primitives styled with tokens; all components in §13.3 (generic ones now; domain composites as their phases arrive) with states (hover, focus-visible, active, disabled, loading, error).
3. App shell: top bar, collapsible sidebar (role-specific nav from §13.4), mobile drawer, command palette (navigation entries now), breadcrumbs, page transition wrapper, toasts, global error boundary, offline banner, skeleton layouts, empty/error states, 403/404/500 pages.
4. **Homepage** exactly as §13.11: sticky navbar, animated hero with word-by-word headline and the 3D "talent constellation" (§13.12), count-up stats strip, scroll-driven "How it works", feature showcase with live mini-animations, clients/developers toggle, interactive fairness-dial demo, research credit, FAQ, final call to action and footer; navigation to login, register (with role preselected), browse projects and legal pages; redirect of signed-in users to their role home; backend `GET /public/stats` (cached 5 min); public project list (screen 6).
5. Restyle Phase 1 auth screens with the design system; password strength meter; OTP input component.
6. **`devsync-ui` project skill (§0.4):** create `.claude/skills/devsync-ui/SKILL.md` (with the built-in `skill-creator`) from §13.1–13.14: responsive rules and component adaptations, tokens, typography, spacing, page-header and card patterns, component usage, motion variants, microcopy, the 3D rules and the consistency system. From now on every frontend task loads it.
7. **Homepage 3D hero (§13.12)**, built with the `threejs-*` skills: `components/three/TalentConstellation.tsx` (instanced nodes, links, pulse, scroll-driven "snap into a team", pointer tilt, newcomer highlight, `Html` result chip), lazy loader with poster cross-fade, `PerformanceMonitor` degradation, pause off-screen, all fallbacks; theme-aware colours read from `design/tokens.ts`.
8. **Still renders (§13.13):** the development-only `/__stills` route and `npm run render:stills` (Playwright) producing `hero-poster.webp` and the in-app stills (light/dark, 1x/2x) plus `stills-manifest.json`; use them on the login/register side panel, empty states, onboarding cards, the 404 page and the social preview image.
9. Storybook is **not** required; instead a `/dev/ui-kit` route (development only, excluded from production build) renders all components and states for visual tests.

**Build — backend:** `/public/stats` (cached 5 min), client error report endpoint (rate-limited, sanitized).

**Security:** §14.13 row 2.

**Tests:** 3D hero: the poster renders before the canvas and the LCP element is the headline; the live canvas appears after load and the scroll "snap" works; with reduced motion, data-saver mode or WebGL disabled (Playwright launched with `--disable-webgl`), only the poster shows and no WebGL context is created; the render loop stops when the hero scrolls off screen (frame counter test); the 3D chunk is not requested on any non-homepage route; no network request leaves the origin (no remote environment maps or models). Homepage E2E: a fresh visit to `/` shows the homepage (not login); every navbar, hero, call-to-action and footer link reaches the right page; "Hire a team" opens registration with Client preselected and "Find work" with Developer preselected; signed-in users opening `/` land on their role home; logout returns to `/`. Homepage Lighthouse thresholds and Core Web Vitals from §13.11 (Lighthouse CI runs in the gate from this phase); the reduced-motion homepage shows final states with no movement; homepage visual baselines (light/dark, 390/1440 px). Component tests for every primitive (keyboard, aria, states); reduced-motion test (variants disabled); contrast tests; Playwright: navigation per role, sidebar collapse persists, command palette opens with keyboard, mobile drawer; axe on all screens; visual baselines for landing, auth screens, UI kit (light/dark, desktop/mobile).

**Gate checks (P2):** responsive viewport matrix (§13.14) passes for every screen built so far, including the homepage, auth pages, app shell, bottom tab bar and mobile menu sheets; bundle size budget (3D chunk ≤ 220 KB gzip, homepage initial JS within the normal budget); no inline scripts/styles in build; visual baselines created; homepage Lighthouse (desktop Performance ≥ 90, mobile ≥ 80, Accessibility ≥ 95) and 60 fps trace with the 3D scene running; stills up to date with the scene and tokens (manifest hash); `devsync-ui` skill present and listed in `docs/plans/phase-02.md`; the ESLint motion rule (no ad-hoc durations) passes.

**Manual check:** browse the landing page and UI kit in light/dark and with reduced motion enabled in OS settings. Then open the homepage on the demo laptop, scroll slowly through the hero and watch the constellation snap into a team; switch to dark mode; enable reduced motion and confirm only the poster shows.

**Acceptance:** gate PASS; design matches §13; zero serious a11y violations.

---

### Phase 3 — Profiles, portfolio, files, skill tests

**Goal:** developers and clients have complete profiles; files are handled safely; newcomers can earn verified skill evidence through timed tests.

**Read first:** §7.2, §10 (Profiles, Skills, Tests, Files), §13.5 screens 7, 14–15, 19, §14.9.

**Build — backend:** models + migrations (§7.2, files); skills taxonomy seed (8 skills, domains); upload pipeline (`uploads/`: streaming, signature check, Pillow re-encode, metadata strip, size/dimension limits, storage, signed URLs, Nginx internal location); profile endpoints; portfolio CRUD with images; certificates and external reviews (pending); skill tests: question bank seed (≥ 15 questions per skill, 10 per attempt, random selection per attempt with seed stored), attempt start (server deadline), answer (only before deadline), submit (score, `skill_evidence`), one scored attempt per 30 days, practice not allowed for tests (to protect the bank); public developer profile with visibility rules.

**Build — frontend:** screens 7, 14 (timed test only; coding UI in Phase 13), 15, 19 (profile & security parts, sessions list, theme, reduced motion); file dropzone with progress; image preview; autosave indicator.

**Security:** §14.13 row 3; answers never sent to client (test asserts response schemas); timer enforced server-side (late answers rejected).

**Tests:** upload security tests (§16.4); profile validation bounds; visibility; test attempt lifecycle (deadline passes mid-attempt, double submit, answer after deadline, retake within 30 days rejected); E2E: developer completes profile with portfolio image, takes a test, sees score on profile; client edits profile.

**Gate checks (P3):** upload of a crafted polyglot rejected; signed URL expires; test answers absent from API responses.

**Manual check:** upload a photo with GPS EXIF, download it, confirm metadata is gone.

**Acceptance:** gate PASS.

---

### Phase 4 — Projects and the CPM planner

**Goal:** clients create complete project plans with a correct, beautiful CPM timeline.

**Read first:** §7.3, §8 (Project, Milestone), §9.10, §10 (Projects), §13.5 screens 21–22, 31.

**Build — backend:** models + migrations (§7.3); `algorithms/cpm.py` (validation, cycle path, forward/backward pass, slack, all critical paths, dates) and `algorithms/forecast.py`; project services (draft CRUD, whole-set replace of slots/milestones/dependencies with validation, plan preview, publish with guards, cancellation rules, baselines); plan endpoints; caching of CPM results per plan version.

**Build — frontend:** Create Project wizard (screen 21, all 6 steps, autosave drafts, unsaved-changes prompt), `DependencyGraph` and `Gantt` composites (keyboard focusable bars, tooltips, table toggle, zoom), CPM table, plan page (screen 22); client "My Projects" list; cancellation dialog (type project title).

**Security:** §14.13 row 4.

**Tests:** CPM hand-calculated textbook cases (≥ 6, including multiple critical paths, single milestone, parallel branches, long chains); cycle detection returns the cycle in order; property tests (no milestone starts before predecessors finish; slack ≥ 0; at least one critical path; durations sum constraints); forecast cases (done, active p>0, active p=0, not started, late predecessors); perf: 300 milestones < 50 ms; API: shares ≠ 100% rejected, > 300 milestones rejected, editing after publish rejected, foreign project 404; E2E: create a 6-milestone project via wizard, see critical path highlighted, publish (after simulated payment verification), cancel a draft.

**Gate checks (P4):** sample plan from §18 produces documented ES/EF/LS/LF values.

**Manual check:** create the "Online ordering system" sample plan (§18.2) and compare the Gantt with the table.

**Acceptance:** gate PASS.

---

### Phase 5 — Marketplace, sealed bidding, filtering *(Demo 1 phase)*

**Goal:** developers find projects and place sealed bids; eligibility follows Algorithm 1 with the newcomer rule; no double booking.

**Read first:** §7.4 (bids, reservations), §9.2, §9.16, §9.17, §9.19, §10 (Marketplace, Bids), §13.5 screens 10–12, 23, §14.5 (sealed bids).

**Reputation dependency (important):** Algorithm 1 needs each developer's $P_i$ and $C_i$, but the full reputation engine is Phase 6. So in this phase create the `reputation_snapshots` table (§7.7) and its read API, implement the **newcomer starting values** (§9.1.3) in `algorithms/reputation.py` (`newcomer_snapshot()` only), and load **fixed, realistic snapshot values** for seeded experienced developers from `backend/scripts/seed_data/stage1_reputation.json` (values listed in §18.4). Filtering reads snapshots only through `services/reputation_read.py`, so Phase 6 can replace the seeded values with computed ones without touching filtering code. The bid table and profiles show these values with a small "seeded" marker in development only.

**Build — backend:** full-text search (tsvector on title/summary/skills; GIN index) with whitelisted filters and cursor pagination; recommended projects (§9.16, cached); bids CRUD with limits and state rules; `algorithms/filtering.py` (Algorithm 1 + newcomer rule + relaxation + advancement ordering + reasons); eligibility dry-run endpoint for the bid sheet; availability reservations (§9.17); bidding deadline job; too-few-bids flow (§9.19) with notifications; client bids view.

**Build — frontend:** Find Projects (screen 10) with URL-synced filters; project details + bid sheet with live eligibility preview (screen 11); My Bids (screen 12, statuses; explanations arrive in Phase 7); client Bids table (screen 23) with too-few-bids banner and actions; public project list (screen 6).

**Security:** §14.13 row 5; sealed-bid tests (every endpoint, every role).

**Tests:** filtering unit tests for each reason code and each paper constraint boundary (equal to threshold passes); newcomer rule; relaxation steps reported; advancement ordering per preset; availability overlap math; search injection corpus; stateful schemathesis (create project → publish → bid → edit → withdraw); E2E (Chromium + mobile): developer filters, opens project, sees "would be filtered" message for an ineligible bid, places a valid bid, edits it; another developer cannot see it; client sees both bids with eligibility.

**Gate checks (P5):** the stage-1 seed (§18.4) shows the documented eligible/ineligible counts and reasons for the "Online ordering system" project.

**Manual check:** log in as two developers and the client in three browser profiles and confirm bid secrecy.

**Acceptance:** gate PASS.

---

### Phase 6 — Reputation engine and market simulator

**Goal:** the [PCS] reputation model implemented exactly, with evidence-based inputs, newcomer starting values, logs and explanations; a deterministic market simulator for tests and experiments.

**Read first:** §7.7 (reputation tables), §9.0, §9.1, §9.14 (trust formula only), §18.

**Build — backend:** `algorithms/reputation.py` (Eq. 1–12 as separate pure functions + `compute_snapshot(history, settings)`; newcomer values; change cap); `services/reputation_inputs.py` (builds inputs from DB; for this phase, inputs come from simulator-generated histories); replace the Phase 5 fixed snapshot values with computed ones (`make seed-demo STAGE=2` regenerates them) and keep `services/reputation_read.py` as the only read path; reputation snapshot/log/skill tables; `GET /developers/{id}/reputation` and `/me/reputation/history`; `scripts/simulate_market.py` (§18.3) generating developers with latent traits and project histories; `docs/PAPER_ALIGNMENT.md` (equation → function → test); `docs/ALGORITHMS.md` reputation section with a worked example.

**Build — frontend:** Reputation page (screen 16) with ReputationPanel, trend chart, explanation log; reputation summary on profile and bid tables.

**Security:** §14.13 row 6.

**Tests:** one named test per ambiguity A1–A13 (§9.0) showing the chosen default and, where a setting exists, the alternative; `pcs_replication` mode switches every extension off (test per extension); each equation with hand-computed fixtures (e.g., ω for project mixes {2,1,1} → 1 − 2/12 = 0.8333; μ for 4 different clients → 1, same client 4× → 0; Eq. 2 EWMA sequence; Eq. 5–8 time-slot and cross-project weighting including α_x < 0.5 behaviour; Eq. 11 with the clip; Eq. 12 weights); property tests (all outputs in [0,1]; monotonicity: a higher rating never lowers β; more distinct clients never lowers μ); newcomer starting values; change cap; settings validation (κ ≤ 0.5 rejected, α_x ≥ 0.5 rejected, weights not summing to 1 rejected); simulator determinism (same seed → identical output); perf: 50-project history < 20 ms.

**Gate checks (P6):** `docs/PAPER_ALIGNMENT.md` lists all Eq. 1–12 with linked tests (script checks every equation id appears in a test name).

**Manual check:** open the reputation page for a seeded experienced developer and a newcomer; explanations make sense.

**Acceptance:** gate PASS.

---

### Phase 7 — Team formation

**Goal:** the research core: fair, explainable, verified team formation.

**Read first:** §7.4 (formation_runs, bid_explanations), §9.2–§9.8, §10 (Formation), §11, §13.5 screens 12, 24, §16.5 step 16.

**Build — backend:** `algorithms/fitness.py` (Eq. 17–19 with breakdown), `algorithms/bpso.py` (Algorithm 2 with repair, locks, archive, early stop, timeout, convergence), `algorithms/exact_solver.py`, `algorithms/fairness.py`, `algorithms/explain.py` (why this team, risks, comparison, why not selected); `services/formation.py` (snapshot candidates + settings + params + seed; enqueue job; persist results; quotas; idempotency); jobs `formation.run` and `formation.explanations` with SSE progress; confirm endpoint creating team + tentative reservations + invitations (Phase 8 handles responses; for now just records); admin verify endpoint.

**Build — frontend:** Team formation screen (screen 24) with PrioritySliders (linked normalization), presets (mapped to advancement choice), minimum standards with live pass count, FairnessDial, run with SSE progress and live ConvergenceChart, result TeamCards (flip-in animation), stat row, "Why this team?" panel, TeamComparison, recalculate, confirm dialog; Why-not-selected card on bid detail (screen 12).

**Security:** §14.13 row 7.

**Tests:** fitness hand examples (two-member and three-member teams); feasibility rules (size, slots, budget, coverage, newcomers, distinct developers); repair invariants (property: every returned solution feasible or infeasible flagged, locks respected); determinism (same seed → same team); PSO vs exact on 200 random small instances: optimal in ≥ 95%, mean gap ≤ 2% (also recorded as experiment E1 data); cost of fairness ≥ 0 and 0 when not binding; explanation correctness (counterfactual price really selects the bid when re-run); timeout returns best feasible; quotas and idempotency; sealed explanations (only bidder/admin); perf (|S| = 200, N = 10 < 5 s); E2E: client runs formation with fairness dial 1 on the seeded "Online ordering system", sees a newcomer selected, cost of fairness shown, verification "Optimal", compares teams, recalculates with Budget preset (team changes), confirms; a non-selected developer reads a correct explanation.

**Gate checks (P7):** seeded project run reproduces the expected team for the fixed seed (stored in fixture); E1 smoke (20 instances) passes.

**Manual check:** run formation with different presets and fairness levels and read the explanations aloud as you would in the viva.

**Acceptance:** gate PASS.

---

### Phase 8 — Invitations, team lead, team repair

**Goal:** turn a formed team into a confirmed team with a lead, and recover gracefully when people decline or leave.

**Read first:** §7.4 (team tables), §8 (Bid, Team member), §9.9, §9.17, §10 (Team), §13.5 screens 9, 25, 33.

**Build — backend:** invitation responses (48 h expiry job), confirmed reservations, lead selection exactly as §1.6 (system recommendation by X_m with tie-breaks; client confirms or picks another accepted member; lead may decline the role; client can change the lead later; members can request a change), lead change requests and lead declining the role, project start transition (activate first milestones, create workspace defaults), team repair (§9.9) with impact and top-3 candidates, reopen slot (48 h), raise budget, member leaving (reason), removal after inactivity (client request + admin approval).

**Build — frontend:** developer dashboard invitation banners with countdown (screen 9), client Team screen (screen 25) with lead recommendation and repair panel, workspace Team tab (screen 33).

**Security:** §14.13 row 8.

**Tests:** lead recommendation ranking and every tie-break (property test: the recommended member always has maximal X_m among accepted members); project cannot start without a client-confirmed lead; expiry job (frozen clock); accept after expiry rejected; one lead per team (DB partial unique + service); repair keeps remaining members and respects budget; impact calculation against CPM; no-candidate reasons; reservation release on decline/leave; E2E: three accept, one declines → repair suggests ranked candidates → client invites → replacement accepts → the system shows the lead recommendation with its reason → client picks a different accepted member (allowed) → that member declines the lead role → system recommends the next member → client confirms → project starts and workspace opens for all; later the client changes the lead and a member submits a lead-change request.

**Gate checks (P8):** scripted decline produces a repair proposal with ≥ 1 candidate on the seed project.

**Manual check:** run the full invite → repair → start flow with four browser contexts.

**Acceptance:** gate PASS.

---

### Phase 9 — Workspace and monitoring

**Goal:** everything a team needs to work, and everything a client needs to see progress and risk — with evidence captured for reputation and no surveillance.

**Read first:** §7.5, §9.1.4–9.1.6, §9.10, §9.11, §10 (Tasks, Check-ins, Discussion, Files, Monitoring), §10.3, §11 (`monitoring.evaluate`, reminders), §13.5 screens 29–36, 38–39.

**Build — backend:** tasks with dependencies (same milestone, acyclic), moves with status rules and positions (fractional indexing), progress calculation, evidence attachments (links validated, never fetched), comments with mentions and revisions, discussion threads/posts, check-ins (one per member per week; on-time flag), project files, activity events (append-only, schemas), forecast snapshots, risk engine (§9.11) with upserts/resolution, team health and overall risk, monitoring dashboard endpoint (cached 30 s, invalidated on events), notifications service (in-app + SSE stream + email outbox for CRITICAL risks and mentions), check-in reminders job.

**Build — frontend:** workspace layout with tabs (role-aware: the client sees every tab read-only except comments/discussion and their own review actions, §1.6); Overview (29), Tasks Kanban with keyboard drag, task drawer, new-task form for lead (30), Timeline with forecast (31), Check-ins (34), Files (35), Discussion with polling (36), Evidence (38, GitHub part arrives in Phase 13), Risks (39); notifications bell + page (18) with SSE; optimistic task moves with rollback.

**Security:** §14.13 row 9; DAST baseline starts.

**Tests:** task dependency rules (DONE blocked until dependencies done), move permissions (assignee vs lead vs other member vs client), progress weights, forecast after moves, each risk rule firing and resolving (frozen clock), team health thresholds, activity event schemas, comment/discussion injection corpus, mention of non-member ignored, file authz, SSE auth/Origin/limits, notification link validation; E2E: lead creates tasks, members drag tasks (mouse and keyboard), post check-ins, comment with mention, upload file; **client progress watching:** the client opens Overview, Timeline, Risks, Milestones and the check-ins feed and sees live progress, but drag handles and task actions are absent and API task moves by the client return 403; a late critical milestone creates a CRITICAL risk with deadline impact; Kanban works on mobile viewport.

**Gate checks (P9):** seeded in-progress project (§18.2 "Inventory dashboard") shows the documented risks and impact (+2 days).

**Manual check:** use "simulate time" in development seed tools (`make seed-demo DAY=12`) and watch risks change.

**Acceptance:** gate PASS; ZAP baseline no high/medium.

---

### Phase 10 — Deliverables, escrow, payments

**Goal:** a correct, tamper-proof money flow from funding to payout, implementing the [PCS] payment policy.

**Read first:** §7.6, §8 (Milestone, Escrow), §9.12, §9.13, §10 (Milestones, Money), §13.5 screens 17, 26, 32, 37, §14.11.

**Build — backend:** ledger accounts/transactions/entries/balances with triggers and constraints; `services/ledger.py` (post balanced transactions with locks and idempotency); wallet deposit (simulated); escrow funding with platform fee and optional bonus pool; milestone submission (lead), approve with rating / request changes (reason) / open dispute; auto-approval job (7 days); contribution splits (proposal, suggestion §9.13, agree/object → dispute, default applied); payouts with `algorithms/payment_policy.py` (Eq. 20–23) and policy details stored; earnings endpoint; client payments overview; `ledger.verify` daily job; CSV export (formula-safe).

**Build — frontend:** Milestones tab with submission and review panels + auto-approval countdown (32); Payments tab with EscrowTimeline, SplitEditor, payouts and policy explanations (37); client Payments page with funding confirm and wallet (26); Earnings page (17); success animations.

**Security:** §14.13 row 10.

**Tests:** every worked example in §9.12.1 as a test with the exact paisa amounts (normal payout, reward, penalty, partial dispute refund, retry, bonus return) and the six reconciliation invariants; payment policy hand examples for each branch (reward with V>c, V≤c → no reward, penalty with ε, on-time vs late, auto-approval rating 4); bonus pool scaling; property tests: random sequences of deposits/funds/releases/refunds keep Σ entries = 0 per transaction and balances = Σ entries; no negative balances; concurrency tests (parallel double-approve, double-fund) → exactly one succeeds; idempotent replay; append-only enforcement; split rounding sums to 10000; E2E: client funds, lead submits, client requests changes, lead resubmits, client approves with 5 stars, members see payouts with reward; another milestone auto-approves after simulated 7 days.

**Gate checks (P10):** `ledger.verify` passes after the E2E run; totals reconcile (client paid = payouts + fee + refunds + escrow remaining).

**Manual check:** trace one milestone's money through the ledger in the admin Payments page (built in Phase 12; until then via `make ledger-report`).

**Acceptance:** gate PASS.

---

### Phase 11 — Reviews, review integrity, reputation updates, post-mortem

**Goal:** close the loop: verified blind reviews and evidence update reputation, protected against manipulation; clients are rated too; every project ends with a post-mortem.

**Read first:** §7.7, §8 (Review), §9.1.4–9.1.5, §9.14, §9.15, §10 (Reviews, Reputation), §11 (`reputation.update_project`, `integrity.scan`), §13.5 screens 40–41.

**Build — backend:** review window opening at REVIEW_WINDOW; three review kinds with category scores; blind visibility (reveal when all expected reviews submitted or window closes); immutability trigger; contests (14 days; weight 0 until decided); reviewer trust computation; consistency check and peer outlier detection; collusion rules R1–R4 and bidding anomaly rules B1–B3 + self-dealing (NetworkX for SCCs); `reputation.update_project` job (builds Γ, Γ_m, internal slots from milestone ratings + final reviews with weights, Eq. 1–12, caps, logs, notifications); client reputation; post-mortem endpoint (planned vs actual, causes from forecast snapshots, team changes, reputation deltas); project completion and bonus pool return.

**Build — frontend:** Reviews tab (40) with blind status and category star inputs; contest dialog; Post-mortem (41); reputation history explanations show project and reasons; client rating on project details (screen 11).

**Security:** §14.13 row 11.

**Tests:** only participants can review; one review per pair; reveal rules (frozen clock); immutability; contests; trust formula; consistency check thresholds; outlier rule; each integrity rule fires on its injected pattern and not on clean simulator data; reputation update end-to-end equals the pure-function result for the same inputs; idempotent job (running twice doesn't double-count); attack simulation smoke (fake ring gains < 30% of undefended gain); E2E: complete a seeded project, all participants review, reviews reveal, reputation changes appear with reasons, post-mortem shows the +2-day delay cause.

**Gate checks (P11):** E4 smoke (attack resistance) and reputation consistency script pass.

**Manual check:** try to leave a revenge review after seeing the other side's review — impossible (blind).

**Acceptance:** gate PASS.

---

### Phase 12 — Disputes and the admin console *(Demo 2 phase)*

**Goal:** fair, auditable dispute resolution and complete platform administration.

**Read first:** §7.8, §8 (Dispute), §10 (Disputes, Admin), §13.5 screens 27, 42–55, §14.4 (step-up, deletion), §14.13 row 12.

**Build — backend:** disputes (categories, automatic evidence snapshot, 72 h statement window, withdraw), admin resolution with outcomes (full, partial %, refund, request revision, new split, remove review) applied through ledger/reputation services in one transaction, decision reason ≥ 20 chars, step-up; admin dashboard aggregates; users (search, suspend/restore, certificate and external review verification); projects (cancel); integrity flag queue (confirm → exclusions + reputation recalc; dismiss → restore); platform alerts; formation runs list/detail/verify; reputation tools (recalculate job); payments overview (ledger search, totals, verify); fairness analytics (real data + simulate job); content admin (skills, question bank CSV import with validation, coding challenges); settings editor with validation, versioning, diff, step-up; audit log viewer and chain verification; user data export job and account deletion.

**Build — frontend:** all admin screens (43–55) with tables, filters, detail panes, confirmation + step-up dialogs, ledger effect previews; client Disputes (27) and project Disputes tab (42); Settings danger zone (export, delete).

**Security:** §14.13 row 12; admin endpoints in the authz matrix; step-up enforced on every sensitive action.

**Tests:** each dispute outcome's money and reputation effects; evidence snapshot immutability; admin cannot resolve own dispute; step-up expiry; settings validation and version history; flag confirm/dismiss effects; export contains only the requester's data (and no secrets); deletion anonymizes PII while ledger/audit remain consistent; last admin cannot be deleted/suspended; E2E: member objects to a split → dispute → admin reviews evidence tabs → partial split decision with TOTP → payouts posted; admin confirms an R1 flag and sees reputation drop.

**Gate checks (P12):** audit chain verifies after the E2E; ledger verify passes.

**Manual check:** walk through the admin console as an examiner would.

**Acceptance:** gate PASS.

---

### Phase 13 — Integrations: GitHub evidence, coding challenges, email

**Goal:** optional evidence and stronger skill verification, with strict isolation.

**Read first:** §7.2 (coding), §7.5 (github_stats), §9.13, §10 (Coding, Monitoring sync), §11, §14.12 (sandbox), §14.13 row 13.

**Build — backend:** `integrations/github.py` (accept only `https://github.com/<owner>/<repo>`; call only `api.github.com`; token from env; pagination limits; ETag caching; circuit breaker; maps commits/PRs/reviews to members via linked usernames; never stores code), sync job + manual sync; contribution split suggestion uses merged PRs; `integrations/judge0.py` (internal URL, auth token, limits, polling with timeout) and coding challenges (practice runs show sample tests; scored submissions run hidden tests; skill evidence); email provider hardening (header injection prevention, bounce-safe outbox).

**Build — frontend:** Evidence tab GitHub section (38) with sync button and last-synced time; coding challenge screen (14) with CodeMirror, run/submit, results.

**Security:** §14.13 row 13.

**Tests:** GitHub client against recorded fixtures (no live calls in CI) — pagination, rate-limit headers, 404 repo, malicious URLs (internal IPs, other hosts, `@` tricks) rejected; circuit breaker; Judge0 client against a fake server; with the real Judge0 container in the integration profile: infinite loop → time limit, fork bomb → bounded, network attempt fails, huge output truncated; email header injection attempts rejected.

**Gate checks (P13):** Judge0 container isolated (attempt to reach `postgres:5432` from a submission fails).

**Manual check:** link a public test repo, sync, see PR counts; solve a coding challenge.

**Acceptance:** gate PASS.

---

### Phase 14 — Performance, scaling and hardening

**Goal:** prove the platform is production-grade under load, failure and attack.

**Read first:** §14 (all), §15 (all), §16.8.

**Build:** production compose profile with `api ×3`, `worker ×2`, PgBouncer, Redis production configuration (separate cache/queue instances or DBs with correct eviction policies), Nginx LB settings; cache-aside on all endpoints listed in §15.1 with invalidation; N+1 query audits (tests asserting query counts on list endpoints); frontend performance (route prefetch, image dimensions, memoization of heavy charts, virtualization for long tables); k6 scripts; chaos scripts; ZAP full baseline with authenticated context; final OWASP Top 10 checklist in `docs/SECURITY.md` with evidence links; Lighthouse CI on landing and dashboard (performance ≥ 90, accessibility ≥ 95, best practices ≥ 95).

**Security:** §14.13 row 14.

**Tests:** §16.8 thresholds; cache invalidation tests (stale data never shown after a write in the same session); rate limits under load; chaos scenarios; Lighthouse thresholds.

**Gate checks (P14):** k6 thresholds met; chaos report written to `runs/chaos/`; ZAP no high/medium; Lighthouse thresholds.

**Manual check:** watch `/metrics` dashboards (or logs) during a k6 run; kill an API replica and keep using the app.

**Acceptance:** gate PASS.

---

### Phase 15 — Experiments, documentation, deployment, demo *(Demo 3 phase)*

**Goal:** evaluation results for the report, complete documentation, a deployable release and a polished demo.

**Read first:** §18, §19, §20, §21, §22.

**Build:** `scripts/run_experiments.py` implementing E1–E9 (§19) with fixed seeds, CSV/JSON outputs and plots (PNG + SVG) in `runs/experiments/<date>/`, plus `docs/EXPERIMENTS.md` generated from outputs (numbers inserted from files, never typed); demo seed (`make seed-demo`) with named accounts and projects in every state (§18.2); production deployment guide and scripts (§20); backups + restore drill; user guides (client, developer, admin) with screenshots from the visual test run; final `README.md` quick start verified in a clean clone; release tag `v1.0.0`.

**Security:** §14.13 row 15; production startup validation exercised in CI with a production-like env.

**Tests:** full gate on all browsers ×3; experiments reproducible (running twice gives identical CSVs); README quick start executed in a temporary clone by the gate; restore drill passes.

**Gate checks (P15):** everything in §22.

**Manual check:** rehearse the demo script (§20.4) end to end.

**Acceptance:** `PHASE 15 GATE: PASS` and the definition of done (§22).

---

## 18. Seed data and the market simulator

### 18.1 Base seed (`make seed-demo`)

Skills (React, Node.js, FastAPI, PostgreSQL, UI/UX, Testing, Flutter, DevOps with domains); question bank (≥ 15 questions per skill); 2 coding challenges; admin `admin@devsync.local` (TOTP printed once); client `rahim@devsync.local` (Rahim's Kitchen); developers (passwords printed once, random): Nadia Rahman (newcomer, React, test score 85%), Arif Hossain (experienced, React/FastAPI/PostgreSQL, 8 projects, 5 clients), Tanvir Ahmed, Sadia Islam, Rafi Karim, Mehjabin Chowdhury (newcomer, Testing 90%), Imran Kabir (7 projects all for one client — R1 pattern), Farhan Siddique, Lamia Akter (newcomer, FastAPI 75%), Shakib Hasan (often late), Nusrat Jahan (strong, 6 projects), Zahid Mahmud (2 projects). Histories are generated by the simulator with fixed seeds so reputations are reproducible.

### 18.2 Demo projects (one per lifecycle state)

1. **Online ordering system** — BIDDING; budget ৳120,000; deadline 30 days; team 4 (React, FastAPI, PostgreSQL, Testing); milestones: Requirements & design 4d; Database 5d (after 1); Backend API 8d (after 2); Frontend 9d (after 1); Integration 3d (after 3, 4); Testing & launch 4d (after 5). CPM: duration 24 days; critical path Requirements → Database → Backend API → Integration → Testing (ES/EF: 0/4, 4/9, 9/17, 17/20, 20/24); Frontend ES 4, EF 13, LS 8, LF 17, slack 4. 12 sealed bids covering all slots, including three newcomers.
2. **Inventory dashboard** — IN_PROGRESS on project day 12; milestones: Requirements 3d (done 0→3), UI design 5d after 1 (done 3→8, 1 revision), Inventory API 7d after 1 (active, started day 4, 70%), Dashboard frontend 8d after 2 (active, started day 8, 40%), Integration 3d after 3 & 4, Testing & handover 4d after 5. Planned duration 23 days (critical path Requirements → UI design → Dashboard frontend → Integration → Testing); forecast 25 days (+2) because the critical Dashboard frontend is late (forecast finish day 18 vs planned 16); Inventory API has used its slack; one member inactive 8 days; a disputed payment split on UI design.
3. **Company website** — REVIEW_WINDOW with partial reviews submitted.
4. A COMPLETED project with post-mortem; a CANCELLED draft; a TEAM_PENDING project with one declined invitation (repair demo).

### 18.3 Market simulator (`scripts/simulate_market.py`)

Developers have latent traits (true skill per domain ~ Beta, reliability, teamwork, communication, price level); ~30% newcomers; clients have budgets and rating strictness. Projects: 3–8 milestones (random DAG, acyclic by construction), slots from skills, budgets consistent with prices. Outcomes: lateness and revisions sampled from latent reliability/skill + noise; client ratings from true performance + strictness + noise; peer ratings from latent teamwork + noise; check-in punctuality and reply times from latent communication. Attack injection (fake accounts, rating rings, revenge reviews, extreme reviews, repeated collusion, shill bids) with ground-truth labels. Output either into the DB (seed) or JSON (experiments). Deterministic per seed; documented in `docs/SIMULATOR.md`; ground truth never shown in the UI.

### 18.4 Stage seeds (`make seed-demo STAGE=N`)

Each stage seed resets the database and loads only what the system can do at that point, so every demo shows real, consistent data.

| Stage | Loaded data |
|---|---|
| **STAGE=1** (Demo 1, after Phase 5) | Admin, Rahim (client, payment method verified), 12 developers from §18.1 with profiles, skills, portfolios and test scores; **fixed reputation snapshots** for experienced developers (table below) and computed newcomer starting values; the "Online ordering system" project in BIDDING with 12 sealed bids (3 newcomers, 2 ineligible with different reasons); one DRAFT project with a deliberate cycle for showing cycle detection; one project with too few bids |
| **STAGE=2** (Demo 2, after Phase 12) | Everything in stage 1, but reputations computed by the Phase 6 engine from simulator histories; plus the "Inventory dashboard" project IN_PROGRESS on day 12 (§18.2), the "Company website" project in REVIEW_WINDOW, one COMPLETED project with post-mortem, a TEAM_PENDING project with a declined invitation, an open split dispute, one R1 integrity flag, wallets and ledger history |
| **STAGE=3** (Demo 3) | Stage 2 plus GitHub evidence fixtures, coding challenge attempts, experiment outputs linked in the admin analytics |

Stage-1 fixed reputation snapshots (`seed_data/stage1_reputation.json`):

| Developer | ω | X | Xm | β | μ | T | C (f = 0.7) | P (0.5, 0.25, 0.25) |
|---|---|---|---|---|---|---|---|---|
| Arif Hossain | 0.78 | 0.86 | 0.77 | 0.84 | 0.80 | 0.70 | 0.80 | 0.80 |
| Nusrat Jahan | 0.72 | 0.82 | 0.81 | 0.86 | 0.72 | 0.74 | 0.75 | 0.80 |
| Tanvir Ahmed | 0.66 | 0.70 | 0.62 | 0.71 | 0.67 | 0.60 | 0.67 | 0.67 |
| Sadia Islam | 0.58 | 0.75 | 0.70 | 0.73 | 0.60 | 0.66 | 0.63 | 0.68 |
| Rafi Karim | 0.62 | 0.64 | 0.58 | 0.66 | 0.63 | 0.58 | 0.63 | 0.63 |
| Imran Kabir | 0.40 | 0.70 | 0.60 | 0.90 | 0.00 | 0.65 | 0.49 | 0.61 |
| Farhan Siddique | 0.55 | 0.60 | 0.55 | 0.62 | 0.67 | 0.52 | 0.57 | 0.61 |
| Shakib Hasan | 0.60 | 0.58 | 0.55 | 0.64 | 0.67 | 0.30 | 0.59 | 0.56 |
| Zahid Mahmud | 0.50 | 0.62 | 0.55 | 0.65 | 0.50 | 0.60 | 0.54 | 0.60 |

(C and P follow Eq. 4 and Eq. 12 with the default weights; the seed script recomputes and asserts them so the table can't drift.) Newcomers (Nadia Rahman, Mehjabin Chowdhury, Lamia Akter) use §9.1.3.

---

## 19. Experiments and evaluation

`make experiments` runs all with fixed seeds and writes CSV + plots + `docs/EXPERIMENTS.md` (generated). Numbers in the report must come from these files.

| ID | Question | Setup | Metrics / plots |
|---|---|---|---|
| E1 | Is BPSO optimal on small instances? | 300 random instances, candidates 8–18, team 3–6, three weight presets | % optimal, mean/max gap vs exact; histogram |
| E2 | Runtime and convergence | candidates 20–200, team 3–10, 30 runs each | p50/p95 runtime, iterations to converge; line plots |
| E3 | Fairness vs top-rated | ≥ 300 simulated jobs; baseline = greedy top (C+P) within budget and slots | newcomer share, Gini of selections, mean fitness, mean latent quality; bar charts |
| E4 | Review attack resistance | inject each attack type; defences on vs off | attacker reputation gain, % reduction, detection precision/recall for R1–R4/B1–B3 |
| E5 | Does reputation track true ability? | 10 simulated rounds | Spearman ρ between reputation and latent traits, with/without evidence and defences |
| E6 | Cost of fairness | min_newcomers 0..2 across E3 jobs | distribution of cost of fairness and price change |
| E7 | Paper metrics | [PCS] settings: 500 workers, team 5–30, task diversity 3–18, deadline 3–15 days, budget per unit, MAX-IT 200 | QoE (Eq. 25), utility (Eq. 24 and U'), task completion ratio, average worker payment vs team size, task diversity, deadline, budget (mirrors the paper's Figs. 3–6 axes); compare DevSync with a greedy baseline |
| E8 | Reputation thresholds | vary P0 / deadline strictness | unreliable-worker detection rate (paper Fig. 7b analogue) |
| E9 | Load | k6 results from Phase 14 | latency/throughput table |

Every experiment page states clearly: simulated data, seeds, settings version, and limitations (not real users).

---

## 20. Deployment and operations

### 20.1 Environments

`development` (hot reload, Mailpit, console SMS, dev certs), `test` (CI, ephemeral, test seed router), `production` (strict validation, real SMTP, no test routes, secrets from Docker secrets).

### 20.2 Production deployment (single VM baseline, documented in `docs/DEPLOYMENT.md`)

Ubuntu LTS VM (≥ 4 vCPU, 8 GB RAM); Docker + Compose; DNS + Let's Encrypt (certbot container or Nginx ACME); `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale api=3 --scale worker=2`; migrations run as a one-off container with the migrator role before starting new API versions; zero-downtime deploys by rolling API replicas; firewall allows only 80/443 (+ SSH from admin IPs); automatic security updates; log rotation.

### 20.3 Backups and runbook

Nightly encrypted `pg_dump` to a separate volume/offsite location; uploads backed up; `make restore-drill` monthly and before the final demo; runbook entries: rotate secrets, revoke all sessions, restore from backup, investigate a ledger mismatch alert, disable a compromised account, scale workers, read the audit log.

### 20.4 Demo script (for the final viva, ~10 minutes)

Landing → login as Rahim → create a plan (show critical path) → open seeded BIDDING project → run team formation with fairness dial 1 (live convergence, "Optimal", cost of fairness) → show "why this team" and comparison → switch to Nadia: invitation and "why not selected" for another developer → open the IN_PROGRESS project: risk dashboard shows +2 days and the critical delay → approve a milestone and show the payout with reward → admin: resolve the split dispute with TOTP, confirm the R1 flag → completed project: post-mortem and reputation changes → fairness analytics vs top-rated.

---

## 21. Documentation deliverables

`README.md` (overview, quick start, commands), `docs/ARCHITECTURE.md`, `docs/PAPER_ALIGNMENT.md`, `docs/ALGORITHMS.md`, `docs/API.md`, `docs/SECURITY.md` (threat model, controls with test links, OWASP checklist, residual risks), `docs/TESTING.md` (how to run each layer; latest gate results), `docs/UI_GUIDE.md` (tokens, components, motion), `docs/SIMULATOR.md`, `docs/EXPERIMENTS.md` (generated), `docs/DEPLOYMENT.md`, `docs/USER_GUIDE_CLIENT.md`, `docs/USER_GUIDE_DEVELOPER.md`, `docs/USER_GUIDE_ADMIN.md`, `docs/AI_ASSISTANCE.md` (disclosure of AI-assisted development as the course requires), `PROGRESS.md`, `DECISIONS.md`.

---

## 22. Definition of done

1. All phases' gates passed; final gate ×3 on all browsers green.
2. Every feature in §1.4 works in the demo seed, verified by E2E tests.
3. Every equation of [PCS] used by DevSync is implemented, tested with hand-computed examples, and mapped in `docs/PAPER_ALIGNMENT.md`; every ambiguity is listed with the supervisor's answer or the documented default.
4. Security: authz matrix complete; all §16.4 tests pass; ZAP and schemathesis clean; scanners clean; OWASP checklist complete; production config validation proven.
5. Performance thresholds (§16.8, §16.5 step 16) met and recorded.
6. Responsiveness: every screen passes the §13.14 viewport matrix and has been checked on a real phone and a 1366×768 laptop. Accessibility: zero serious/critical axe violations on all screens; keyboard-only walkthrough of the core journey recorded in `docs/TESTING.md`.
7. Experiments E1–E9 generated reproducibly; report numbers come only from outputs.
8. Documentation (§21) complete; README quick start verified in a clean clone.
9. Backups and restore drill verified.
10. Each team member can explain their modules (plain-English docs exist for every algorithm and security control).

---

## 23. Open questions for the supervisor

Ask early (Phase 6 at the latest) and record answers in `DECISIONS.md`; until answered, use the defaults in §9.0.

1. Timeliness direction (A1) and late-submission handling (A2).
2. Value for wrong-size teams in Eq. 17 (A3).
3. Initial communication value Γ⁰ (A4) and the meaning of "ω + X = 1" (A5).
4. Older projects weighted more across projects (A6): intended?
5. Should performance P also enter the fitness function (A7)?
6. Source and verification of external reviews (A8).
7. ω and μ for workers with fewer than 2 projects/hires (A9).
8. The normalizer C in Eq. 18 (A10).
9. The sign in the penalty factor ε, Eq. 23 (A11).
10. The utility function Eq. 24 (A12).
11. Inertia in Eq. 14 (A13).
12. Is the newcomer rule (challenge score instead of performance threshold) acceptable as an extension?
13. Is the target "cost of fairness ≤ 5%" reasonable, given early simulation suggested larger costs?

---

## 24. First message to the student

After reading sections 0–1 and §17.0, say exactly what you will do in Phase 0, confirm the demo dates in §17.0, list any questions about this specification, remind the student to turn on Plan Mode and to place the paper PDF in `docs/papers/`, and wait for approval before creating any files.
