# Security review — Phase 6 (reputation engine and market simulator)

- **Date:** 2026-11-21
- **Reviewer:** Claude Code (`/security-review` method on `main...phase-6`), with Raisa Tabassum.
  The review traced every new route, RLS policy, migration grant, service read path and
  frontend rendering path against the Phase 1–5 patterns; findings filtered at confidence ≥ 8/10.
- **Scope:** migration `0012_reputation_engine` (`reputation_history`, `reputation_skill`,
  append-only `reputation_log`, `reputation_snapshots.simulated`, the tightened snapshot write
  policy); `algorithms/reputation.py`, `reputation_explain.py`, `trust.py`, `simulator.py`;
  `services/reputation_inputs.py`, `reputation_engine.py`, `reputation.py`, the changes to
  `reputation_read.py`; the `reputation.recalculate_all` job; `GET /developers/{id}/reputation`
  and `GET /me/reputation/history` with the `reputation.history` policy; the test-only
  history-seeding route; the stage-2 seed and the simulator CLI; the Reputation page and its
  charts.
- **Tester's human check (spec §14.22):** _pending_ (Sara): sign in as a developer, another
  developer and a client; confirm the history is visible only to its developer and that a
  clients-only profile's reputation is 404 for developers.

Unresolved high findings: 0

## Result of the review

No high- or medium-confidence vulnerabilities were found. The §14.13 row 6 control —
reputation inputs only from server-side evidence — holds at three layers.

| Area | Conclusion |
|---|---|
| Nobody but the engine writes reputation | The API has no write method on reputation (POST/PUT/PATCH/DELETE → 405, tested). All four reputation tables are SYSTEM-write under RLS with `is_system()`, which also requires the worker's login role, so a web connection that set `app.role = SYSTEM` would still be refused (tested for snapshots and history). Migration 0012 tightened 0006's snapshot write policy the same way (D99). |
| Change log integrity | `reputation_log` is append-only: a row trigger refuses UPDATE and DELETE for every role (tested even for SYSTEM), and the app roles hold no UPDATE/DELETE/TRUNCATE grant. Re-runs insert nothing (unique key + ON CONFLICT DO NOTHING). |
| Privacy of history and evidence | History and log rows are readable by the developer and admins only (RLS), and the history route is developer-only and scoped to the caller. The newcomer basis (verified items, evidence domains) is computed and returned only when the caller is the developer. Another user's newcomer without a snapshot gets nulls, never an on-the-fly value computed from that developer's private data (D58, D101). |
| Profile visibility | `GET /developers/{id}/reputation` checks visibility first through the existing `public_developer_profile` definer in the caller's session: hidden, unknown and non-developer ids → 404 (tested). |
| Injection | All queries are ORM/Core with bound parameters; the history cursor is base64 → typed ISO time + UUID, and garbage is a typed 422. Migration DDL is built from constants only. |
| Output encoding | Change explanations are built server-side from SYSTEM-written rows and rendered by React as text; the SVG charts set only numeric attributes and token classes; no `dangerouslySetInnerHTML` and no injected styles (strict CSP unchanged). |
| Test-only route | `/__test__/developers/{id}/reputation-history` exists only when `DEVSYNC_ENV=test`; `assert_no_test_routes` refuses startup elsewhere; the body is a `StrictRequest` with bounded integers. |
| Simulator ground truth | Latent traits never leave the simulator: only §9.1.1 inputs are stored (tested). Simulated values are labelled in the UI and the API (`simulated`). |
| Settings | Reputation weights are validated on save (κ > 0.5, α_x and α_e < 0.5, sums = 1, cap > 0; tested). |

## Findings fixed during the phase

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Low (defence in depth) | 0006's `reputation_snapshots` write policy accepted `app_role() = 'SYSTEM'` on any database role, so the database relied on the application never setting SYSTEM on a web connection. | **Fixed (D99):** `is_system()` (worker login role) for every reputation write policy; tested with the web role claiming SYSTEM. |
| 2 | Low (correctness of a security-relevant input) | The newcomer Γ⁰ ignored admin-verified certificates although §9.1.3 lists them. | **Fixed (D94):** counted only once an admin verified the certificate; a pending one doesn't count (tested). |

## Accepted, not changed

- Per-skill competency (`reputation_skill`) is a public read for signed-in users, like the
  snapshot (D58). For a clients-only profile the API answers 404 to developers, while the
  database still lets a signed-in user read the row directly. This is the same accepted model as
  the Phase 5 snapshot and exposes nothing the snapshot doesn't.
