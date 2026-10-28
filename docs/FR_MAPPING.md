# Requirement ID mapping (proposal ↔ spec)

The spec is the full, authoritative feature list; the proposal
(`docs/design/DevSync_Proposal_final.pdf`) is a trimmed, renumbered subset. Test names use
spec IDs. This table is completed as each phase implements the features.

| Proposal ID | Proposal summary | Spec section | Phase |
|---|---|---|---|
| FR-AUTH-1..6 | Registration, phone OTP, email verify, reset, admin 2FA, settings | §1.4 Accounts, §14.4 | 1 |
| FR-PROF-1..5 | Developer/client profiles, certificates, skills list | §1.4 Profiles, §7.2 | 3 |
| FR-CHAL-1..4 | Timed MCQ tests (now practice tests), evidence, newcomer use (now the role assessment, FR-RA), admin portfolio review | §1.4 Skill challenges | 3, 13 |
| FR-MKT-1..5 | Landing, search, cards, details, recommendations | §13.11, §9.16 | 2, 5 |
| FR-PROJ-1..6 | Wizard, milestones, CPM, graph + Gantt, plan changes, baseline vs forecast | §9.10, §13.5 | 4, 9 |
| FR-BID-1..3 | Sealed bids, Algorithm 1 filtering, newcomer rule | §9.2 | 5 |
| FR-RA-1 | Role assessment blueprint per project slot (rule-based, frozen at publish) | Role assessment spec §5.1, §4.3–4.4 | 5 (Demo 1 addition) |
| FR-RA-2 | Timed one-way assessment with focus mode and the two-leave rule | Role assessment spec §6–§7 | 5 (Demo 1 addition) |
| FR-RA-3 | Difficulty-weighted scoring with a per-competency floor; reuse 180 days, retake 30 days | Role assessment spec §5.3, §6.7 | 5 (Demo 1 addition) |
| FR-RA-4 | Newcomer bids need a valid pass; Algorithm 1 uses the result; client sees the result line | Role assessment spec §8 | 5 (Demo 1 addition) |
| FR-RA-5 | Admin review queue, void with step-up, accommodations, question-bank review | Role assessment spec §12 | 5 (UI for accommodations and bank review after Demo 1) |
| FR-RA-6 | Self-verified question bank with execution checks and blind second solves; team review after Demo 1 | Role assessment spec §13 | 5 |
| FR-TEAM-1..7 | Formation dashboard, sliders, BPSO, why this team, why not selected, exact check, invitations | §9.3–§9.8 (proposal FR-TEAM-3 = spec FR-TEAM-4) | 7 |
| FR-INV-1..5 | Invitations, lead selection, lead change, repair, replacement | §1.6, §9.9 | 8 |
| FR-MON-1..10 | Workspace, Kanban, check-ins, files, GitHub, dashboard, risks, evidence | §9.11, §13.5 | 9, 13 |
| FR-DEL-1..4 | Evidence, submission, approve/changes, dispute | §8 Milestone | 10 |
| FR-PAY-1..5 | Wallet, escrow, splits, payment policy | §9.12–§9.13 | 10 |
| FR-REV-1..2 | Blind reviews, weights and flags | §9.14 | 11 |
| FR-REP-1..7 | Reputation model, evidence inputs, updates, dashboard, settings, newcomers, recalc | §9.1 | 6, 11 |
| FR-DIS-1..4 | Disputes, evidence, admin decisions | §8 Dispute | 12 |
| FR-POST-1..2 | Post-mortem | §13.5 #41 | 11 |
| FR-ADM-1..5 | Admin dashboard, users, queues, runs, fairness analytics | §13.5 #43–55 | 12 |
