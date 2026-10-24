# Product backlog

One line per item: id · title · phase · priority · status · owner. Spec feature IDs are the
authority; proposal IDs are mapped in `FR_MAPPING.md`.

| ID | Title | Phase | Priority | Status | Owner |
|---|---|---|---|---|---|
| P0-1 | Repository, CLAUDE.md, PROGRESS, DECISIONS, docs stubs | 0 | Core | done | Taeen |
| P0-2 | Config with production validation, logging redaction, safe errors | 0 | Core | done | Taeen |
| P0-3 | Migration 0001: settings, hash-chained append-only audit log, jobs, idempotency | 0 | Core | done | Taeen |
| P0-4 | Nginx TLS/headers/limits/timeouts; Compose with hardening; DB roles | 0 | Core | done | Taeen |
| P0-5 | Phase gate, forbidden-pattern scanner, layer checker, OpenAPI linter, RLS checker | 0 | Core | done | Taeen |
| P0-6 | Frontend scaffold, tokens, contrast test, CSP-safe build, Playwright smoke | 0 | Core | done | Taeen |
| P0-7 | CI workflow, pre-commit, Dependabot | 0 | Core | done | Taeen |
| P0-8 | Design skills installed and reviewed (§0.4) | 0 | Core | done | Taeen |
| P0-9 | Full gate PASS | 0 | Core | done | Taeen |
| P1-* | Accounts, authentication, sessions, security core | 1 | Core | done | Taeen |
| P2-1 | Tokens, theme and motion providers, motion lint rule | 2 | Core | done | Taeen |
| P2-2 | Component library (generic §13.3 components) + UI kit | 2 | Core | done | Taeen |
| P2-3 | App shell: role sidebars, tab bar, command palette, toasts, error/offline states | 2 | Core | done | Taeen |
| P2-4 | Homepage (§13.11) with 3D hero, stills, social preview | 2 | Core | done | Taeen |
| P2-5 | Auth screens restyled; password rules shown up front | 2 | Core | done | Taeen |
| P2-6 | `/public/stats`, `/client-errors` | 2 | Core | done | Taeen |
| P2-7 | devsync-ui skill | 2 | Core | done | Taeen |
| P3-1 | Migration 0004: profiles, skills, files, portfolio, certificates, external reviews, question bank, attempts, evidence (RLS, guard triggers, definers) | 3 | Core | done | Taeen |
| P3-2 | Upload pipeline (signatures, polyglot/PDF checks, re-encode, signed URLs, X-Accel downloads) | 3 | Core | done | Taeen |
| P3-3 | Profile & portfolio, certificates, external reviews, public profile `/d/:id`, client organisation | 3 | Core | done | Taeen |
| P3-4 | Timed skill tests (8 skills, 128 questions), evidence, expiry and cleanup jobs | 3 | Core | done | Taeen |
| P3-5 | Human review of the 128 drafted questions (D34) | 3 | Core | todo | team |
| P4-1 | Pure CPM + forecast algorithms (§9.10), 300 milestones < 50 ms | 4 | Core | done | Salwa |
| P4-2 | Migration 0005: projects, slots, milestones, dependencies, baselines (RLS, publish-guard and baseline triggers) | 4 | Core | done | Salwa |
| P4-3 | Project API: drafts, whole-set replaces, publish guards, If-Match, cancel, extend bidding, simulated payment verification (D39) | 4 | Core | done | Salwa |
| P4-4 | 6-step wizard with live CPM preview, plan page (Gantt, dependency graph, CPM table), My Projects | 4 | Core | done | Salwa (review fixes: Taeen, D43) |
| P4-5 | ERD generator (`make erd`) → `docs/design/erd.svg` | 4 | Core | done | Salwa |
| P4-6 | Gantt polish: date axis, dependency arrows, legend, zoom, today line, full names | 4 | Expected | done | Taeen |
| P5-1 | Migrations 0006/0007: bids, reservations, reputation snapshots, project search, bidding terms; sealed-bid RLS | 5 | Core | done | Salwa / Taeen |
| P5-2 | Pure Algorithm 1 filtering + newcomer rule + relaxation + shortlist, availability, explanations | 5 | Core | done | Salwa / Taeen |
| P5-3 | Marketplace: search with filters and keyset paging, public list, recommendations (§9.16) | 5 | Core | done | Salwa / Taeen (D54) |
| P5-4 | Sealed bids: place/edit/withdraw, live eligibility preview, My Bids, client Bids view with reasons | 5 | Core | done | Salwa |
| P5-5 | Too-few-bids handling: banner, extend, cancel, change terms with preview, reminder + auto-close (§9.19, D54) | 5 | Core | done | Taeen |
| P5-6 | Demo-1 tooling: stage-1 seed, demo reset/up/preflight/check, walkthrough E2E | 5 | Core | done | Taeen |
| P5-7 | Cross-browser E2E (chromium, firefox, webkit, mobile) ×3 | 5 | Core | done | Taeen |
| D1-1 | Demo 1 rehearsal on the demo laptop; mkcert certificate (D3); `make demo-preflight` | 5 | Core | todo | team |
| D1-2 | Tester's human check of security reviews 00–05 | 5 | Core | todo | Sara |
| D1-3 | Release tag `v0.1.0` at Demo 1 (§17.1) | 5 | Core | todo | Taeen |
| P6-0 | Move laptops and the Nginx build stage to Node 22 LTS (D15) | 6 | Core | todo | — |
| P7-H | Homepage example figures from a real PSO run (`build_homepage_example.py`, % chip, gate freshness check; D21) | 7 | Core | todo | — |

## Functional requirements (proposal FR-IDs, see `FR_MAPPING.md`)

Status as of 24 Oct 2026 (end of Phase 5). *done* = built, tested and behind a passing gate;
*partial* = part built, the rest named in the notes; *planned* = not started.

| FR | Requirement (short) | Phase | Priority | Status | Notes |
|---|---|---|---|---|---|
| FR-AUTH-1 | Register as client or developer; admins created by admins | 1 | Core | done | `make create-admin`; admin-creates-admin screen in Phase 12 |
| FR-AUTH-2 | Phone OTP, one account per phone | 1 | Core | done | SMS simulated (console/noop) until Phase 15 |
| FR-AUTH-3 | Email verification link | 1 | Expected | done | |
| FR-AUTH-4 | Password reset by email | 1 | Expected | done | Reset revokes all sessions |
| FR-AUTH-5 | Admin two-factor login | 1 | Core | done | TOTP, recovery codes, step-up |
| FR-AUTH-6 | Settings: password, notification preferences, profile visibility | 1, 3, 9 | Expected | partial | Password, sessions and profile visibility done; notification preferences come with the inbox (Phase 9) |
| FR-PROF-1 | Developer profile: bio, skills, availability, GitHub, portfolio | 3 | Core | done | Autosave, drag reorder, screenshots |
| FR-PROF-2 | Certificates with admin verification and badge | 3, 12 | Expected | partial | Upload and badge done; admin verification screen in Phase 12 (DB rule D35 already in place) |
| FR-PROF-3 | Profile shows reputation, scores, history, portfolio, newcomer badge | 3, 6, 11 | Core | partial | Skill evidence, portfolio, certificates, newcomer badge done; reputation (C, P, newcomer, seeded note; D58) on profiles and in the bids view; full reputation model and project history in Phases 6/11 |
| FR-PROF-4 | Client profile with organisation and project history | 3, 11 | Core | partial | Organisation done; project history once projects complete |
| FR-PROF-5 | Skills from a fixed, admin-managed list | 3, 12 | Core | partial | Fixed, read-only taxonomy; admin editing in Phase 12 |
| FR-CHAL-1 | Timed MCQ tests from a randomised, admin-managed bank | 3, 12 | Core | partial | Tests done (128 seeded questions, human review pending, D34); admin bank editor ("Content" page) not built yet |
| FR-CHAL-2 | Score becomes verified skill evidence | 3 | Core | done | |
| FR-CHAL-3 | Scores set a newcomer's expertise and let newcomers pass filtering | 3, 5 | Core | done | Newcomer rule in Algorithm 1 |
| FR-CHAL-4 | Admin portfolio review when the sandbox is unavailable | 13 | Expected | planned | |
| FR-MKT-1 | Public landing page | 2 | Core | done | 3D hero; no algorithm figures until Phase 7 (D21) |
| FR-MKT-2 | Search and filter (skill, budget, deadline, role, team size, availability) | 5 | Core | done | Text, skills, budget range, deadline, role, team size, hours a week (the §9.17 availability check) and sort; every filter kept in the address |
| FR-MKT-3 | Project cards with View project and Bid | 5 | Core | done | |
| FR-MKT-4 | Project details with milestone list and states | 5, 9 | Core | done | Description, client, budget, slots (own skills highlighted), milestone list with states and a mini Gantt on the developer's project page |
| FR-MKT-5 | Recommended projects | 5 | Expected | done | On Find Projects (§9.16, D54) |
| FR-PROJ-1 | Multi-step creation wizard | 4 | Core | done | 6 steps, live CPM preview |
| FR-PROJ-2 | Milestones with duration, skills, share (Σ 100 %) | 4 | Core | done | Enforced in service and DB |
| FR-PROJ-3 | CPM: ES/EF/LS/LF, slack, critical path | 4 | Core | done | Pure `cpm.py` |
| FR-PROJ-4 | Dependency graph + Gantt + table | 4 | Core | done | Gantt polished 23 Oct |
| FR-PROJ-5 | Plan changes need client + lead agreement, new baseline | 9 | Expected | planned | `plan_change_requests` table exists |
| FR-PROJ-6 | Baseline vs forecast | 9 | Expected | planned | Pure `forecast.py` exists |
| FR-BID-1 | One sealed bid per project with slot, price, days, proposal, portfolio, contribution | 5 | Core | done | Edit and withdraw included |
| FR-BID-2 | Algorithm 1 filtering with reasons | 5 | Core | done | "How the filter decided" |
| FR-BID-3 | Newcomer rule | 5 | Core | done | |
| FR-TEAM-1 | Formation dashboard | 7 | Core | planned | |
| FR-TEAM-2 | Priority sliders / presets | 7 | Core | planned | |
| FR-TEAM-3 | BPSO team selection | 7 | Core | planned | |
| FR-TEAM-4 | "Why this team?" and team risks | 7 | Core | planned | |
| FR-TEAM-5 | "Why not selected" | 7 | Expected | planned | |
| FR-TEAM-6 | Saved runs + exact solver (≤ 18) | 7 | Core | planned | |
| FR-TEAM-7 | Confirming sends invitations | 7, 8 | Core | planned | |
| FR-INV-1 | 48-hour invitations | 8 | Core | planned | Re-check availability on acceptance (D54) |
| FR-INV-2 | Team lead recommendation, client decides | 8 | Core | planned | |
| FR-INV-3 | Lead change / decline | 8 | Expected | planned | |
| FR-INV-4 | Team repair with ranked candidates | 8 | Core | planned | |
| FR-INV-5 | Replacement inherits work; payments recalculated | 8, 10 | Expected | planned | |
| FR-MON-1 | Workspace tabs | 9 | Core | planned | |
| FR-MON-2 | Kanban board | 9 | Core | planned | |
| FR-MON-3 | Task fields | 9 | Core | planned | |
| FR-MON-4 | Milestone progress from tasks | 9 | Core | planned | |
| FR-MON-5 | Weekly check-ins, inactivity warning | 9 | Core | planned | |
| FR-MON-6 | Shared files area | 9 | Expected | planned | Upload pipeline and Nginx upload route ready |
| FR-MON-7 | GitHub evidence | 13 | Expected | planned | |
| FR-MON-8 | Monitoring dashboard | 9 | Core | planned | |
| FR-MON-9 | Risk dashboard | 9 | Core | planned | |
| FR-MON-10 | Activity evidence events | 9 | Core | planned | |
| FR-DEL-1 | Task evidence | 10 | Expected | planned | |
| FR-DEL-2 | Milestone submission by the lead | 10 | Core | planned | |
| FR-DEL-3 | Approve with rating / request changes | 10 | Core | planned | |
| FR-DEL-4 | Dispute instead of approving | 10, 12 | Core | planned | |
| FR-PAY-1 | Simulated wallet and history | 10 | Core | planned | Payment-method verification is already simulated (D39) |
| FR-PAY-2 | Payment dashboard with milestone states | 10 | Core | planned | |
| FR-PAY-3 | Escrow funding with platform fee | 10 | Core | planned | |
| FR-PAY-4 | Contribution splits with suggestion | 10 | Expected | planned | |
| FR-PAY-5 | Release with [PCS] payment policy | 10 | Core | planned | |
| FR-REV-1 | Blind participant reviews | 11 | Core | planned | |
| FR-REV-2 | Review weights and integrity flags | 11 | Core | planned | |
| FR-REP-1 | [PCS] reputation model | 6 | Core | planned | Phase 5 uses seeded snapshots (D44) |
| FR-REP-2 | Parameters from evidence after integrity checks | 6, 11 | Core | planned | |
| FR-REP-3 | Updates after projects and disputes | 11, 12 | Core | planned | |
| FR-REP-4 | Reputation dashboard | 6 | Core | planned | |
| FR-REP-5 | Weights as settings; switchable calculation | 6 | Core | planned | |
| FR-REP-6 | Newcomer starting values | 5, 6 | Core | partial | `newcomer_snapshot()` computed since Phase 5; full model in Phase 6 |
| FR-REP-7 | Admin recalculation | 6, 12 | Expected | planned | |
| FR-DIS-1 | Open a dispute | 12 | Core | planned | |
| FR-DIS-2 | Dispute screen with automatic evidence | 12 | Core | planned | |
| FR-DIS-3 | Admin decisions with reasons | 12 | Core | planned | |
| FR-DIS-4 | Payments and reputation wait for the decision | 12 | Core | planned | |
| FR-POST-1 | Post-mortem: planned vs actual | 11 | Expected | planned | |
| FR-POST-2 | Causes of delays from forecast history | 11 | Expected | planned | |
| FR-ADM-1 | Admin dashboard | 12 | Core | planned | Admin home and 2FA setup exist; other admin pages show "coming in Phase N" |
| FR-ADM-2 | Users: search, history, verify certificates, suspend/restore | 12 | Core | planned | |
| FR-ADM-3 | Queues: disputes, flags, alerts | 11, 12 | Core | planned | |
| FR-ADM-4 | Formation runs with exact check | 7, 12 | Expected | planned | |
| FR-ADM-5 | Fairness analytics | 12 | Expected | planned | |

Spec-only items not in the proposal (spec §1.4): data export and account deletion (Phase 12),
notification inbox and preferences (Phase 9; notifications are already written since Phase 5),
market simulator (Phase 6), experiments E1–E9 (Phase 15).
