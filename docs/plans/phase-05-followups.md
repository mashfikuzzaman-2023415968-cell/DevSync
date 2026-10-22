# Phase 5 follow-ups (after the external review) — plan and record

Approved by Taeen on 2026-10-22 ("do everything that's mentioned"); decisions in DECISIONS D54,
security in `docs/security-reviews/phase-05.md` (findings 6–8 and the new surfaces).

Phase 5 had passed its gate and been merged and tagged. An external review of the build listed
correctness gaps, spec gaps on the Demo 1 screens and design questions. This branch
(`phase-5-followups`) closes all of them and is tested end to end — full gate, security review,
Demo-1 readiness check and repeated cross-browser runs of every changed screen — before it is
merged into `main` and pushed.

## Correctness
- Bidding closes by time on every bid write and the preview, not only when the deadline job runs.
- A bid may attach only the bidder's own portfolio items.
- Sign-in accepts reserved-domain addresses (the seeded `@devsync.local` demo accounts); demo
  preflight signs in for real.
- Changes after bids exist go only through the too-few-bids actions, extend and cancel.
- `pcs_replication` relaxes the thresholds only when no bid qualifies, as [PCS] Algorithm 1 does.
- A shortfall left alone: a reminder after 7 days, automatic closing after 14 (date shown).
- D47 corrected.

## Demo screens (client Bids, bid sheet)
- Every verdict explained check by check (Algorithm 1 trace), the newcomer rule named with the
  test score, automatic relaxation shown with its step, the cheapest eligible team against the
  budget, filters by slot and eligibility, cards on phones and tablets.
- "Fix the shortfall": extend, lower standards (floors), raise budget (only up), reduce team
  (only down), cancel — each previewing its effect before it is confirmed; bidders notified.
- Bid sheet: hours a week, expected contribution, up to three own portfolio items, closed state.

## Behind the scenes
- Search: keyset pagination for every sort; skill names in the text search.
- Recommendations per §9.16: typical days, free hours, 5-minute cache.
- Evaluation reads bidder data in batches (7 queries for 200 bids; perf test).
- Homepage hero shows the poster when WebGL would run in software; live-3D tests on the GPU.
- E2E: withdraw and re-bid, newcomer path, relaxation, the fix-the-shortfall flow, closed bidding,
  Demo-1 walkthrough updated; visual baselines for the bidding screens.
- Property tests for Algorithm 1 (determinism, monotone thresholds, partition, shortlist bound,
  explanation agrees with the verdict, cheapest team is the true minimum).

## Found on the way
- The bundled breached-password list was gitignored and never committed (now tracked).
- The client view read ORM rows after its SYSTEM session closed (500).
- The shared dialog close button shrank on narrow screens.
- `demo-check` could leave the test stack without the demo seed.

## Known limitations (documented)
TOO_SLOW uses the whole-project deadline; availability is re-checked at invitation acceptance in
Phase 8; bid prices stay visible to the client during bidding (spec), sealed from developers.
