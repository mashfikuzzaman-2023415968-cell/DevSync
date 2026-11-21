# PAPER ALIGNMENT

Maps every [PCS] equation/algorithm to its DevSync function and test, labelled *exact*, *exact
with a documented resolution (A#, §9.0)* or *DevSync extension*. Filled as each phase builds it.

## Phase 5

| Paper element | Status | Function | Tests |
|---|---|---|---|
| Algorithm 1 — worker filtering ([PCS] §4.2) | exact, with the newcomer rule, relaxation and advancement as **DevSync extensions** (off in `pcs_replication`) | `app/algorithms/filtering.py::filter_bids` | `tests/algorithms/test_filtering.py` |
| Newcomer starting values (ours; A4, A9) | DevSync extension | `app/algorithms/reputation.py::newcomer_snapshot` | `tests/algorithms/test_reputation_newcomer.py` |
| Availability reservations (ours, §9.17) | DevSync extension | `app/algorithms/availability.py` | `tests/algorithms/test_availability.py` |

## Phase 6 — reputation (Eq. 1–12, [PCS] §4.1)

All in `backend/app/algorithms/reputation.py`; arithmetic in `Decimal`, stored to 3 places (D85).
`scripts/check_paper_alignment.py` (gate, phase 6 checks) verifies that every row names an
existing function and that a test name contains the equation id (`eqNN`).

| Paper element | Status | Function | Tests |
|---|---|---|---|
| Eq. 1 ω, Simpson diversity over domains | exact with documented resolution (A9: N < 2 uses ω⁰ from skill evidence, D88) | `eq01_omega` | `test_eq01_omega_spec_example_2_1_1`, `test_eq01_omega_single_domain_is_zero_and_all_distinct_is_one`, `test_eq01_omega_refuses_fewer_than_two_projects_and_negative_counts`, `test_A9_omega_and_mu_below_two_projects` |
| Eq. 2 X, communication EWMA | exact with documented resolution (A4: X⁰ = Γ⁰ from verification; change cap is a DevSync extension, D86) | `eq02_communication` | `test_eq02_communication_ewma_sequence`, `test_eq02_communication_boundaries_and_invalid_input`, `test_A4_initial_communication_from_verification` |
| Eq. 3 X_m, teamwork EWMA | exact (change cap is a DevSync extension, D86) | `eq03_teamwork` | `test_eq03_teamwork_ewma_sequence`, `test_eq03_teamwork_refuses_out_of_range` |
| Eq. 4 C = f·ω + (1 − f)·X | exact with documented resolution (A5: f and 1 − f sum to 1) | `eq04_competency` | `test_eq04_competency_weights`, `test_A5_competency_weights_sum_to_one` |
| Eq. 5 E, external reviews within a project | exact | `eq05_external_within` | `test_eq05_external_within_project_slots`, `test_eq05_external_within_needs_a_rating` |
| Eq. 6 I, internal reviews within a project | exact | `eq06_internal_within` | `test_eq06_internal_within_project_slots`, `test_eq06_internal_within_recent_slot_dominates` |
| Eq. 7 λ, internal reviews across projects | exact with documented resolution (A6: α_x < 0.5, older projects weigh more) | `eq07_internal_across` | `test_eq07_internal_across_projects`, `test_eq07_older_projects_weigh_more_with_alpha_x_below_half`, `test_A6_older_projects_weigh_more` |
| Eq. 8 ε, external reviews across projects | exact with documented resolution (A6; projects without externals skipped, D87) | `eq08_external_across` | `test_eq08_external_across_projects`, `test_eq08_external_across_refuses_out_of_range` |
| Eq. 9 β = w_y·λ + w_x·ε | exact with documented resolution (A8: no verified externals → β = λ) | `eq09_beta` | `test_eq09_beta_weights_internal_over_external`, `test_eq09_beta_without_external_reviews_is_lambda`, `test_A8_beta_uses_internal_reviews_only_without_verified_externals` |
| Eq. 10 μ, re-employment diversity | exact with documented resolution (A9: N^r < 2 → neutral 0.5) | `eq10_mu` | `test_eq10_mu_four_different_clients_is_one`, `test_eq10_mu_same_client_four_times_is_zero`, `test_eq10_mu_mixed_and_invalid` |
| Eq. 11 T, timeliness | exact with documented resolution (A1: as written, faster = higher; A2: each ratio clipped to 1) | `eq11_timeliness` | `test_eq11_timeliness_two_projects`, `test_eq11_timeliness_clip_late_work_contributes_zero`, `test_eq11_timeliness_invalid_input`, `test_A1_timeliness_direction`, `test_A2_late_work_is_clipped` |
| Eq. 12 P = g1·β + g2·μ + g3·T | exact | `eq12_performance` | `test_eq12_performance_default_weights`, `test_eq12_performance_other_weights_and_invalid` |
| Whole model over a history | exact composition of Eq. 1–12 | `compute_snapshot` | `tests/algorithms/test_reputation_snapshot.py` (worked example, replication), `tests/property/test_reputation_properties.py` |
| Change cap ±0.15 per project on X, X_m, β | DevSync extension (off in `pcs_replication`) | `apply_change_cap` | `test_change_cap_clamps_both_ways`, `test_replication_switches_off_the_change_cap`, property `test_change_cap_holds_for_x_xm_beta_and_never_touches_omega_mu_t` |
| Per-skill competency C_{i,s} (§9.1.7) | DevSync extension (off in `pcs_replication`; D97) | `skill_competency` | `test_worked_example_skill_competency`, `test_skill_competency_evidence_floor_only_for_newcomers`, `test_replication_switches_off_skill_competency` |
| Reviewer trust and weighted means (§9.14 formula) | DevSync extension (all weights 1 in `pcs_replication`; D90) | `app/algorithms/trust.py::reviewer_trust`, `weighted_mean` | `tests/algorithms/test_trust.py` |
| Plain-language explanations | DevSync extension | `app/algorithms/reputation_explain.py::explain_change` | `tests/algorithms/test_reputation_explain.py` |

### `pcs_replication` in reputation (D89)

Off: the change cap, the §9.1.3 newcomer starting values (the paper's "set to zero": Γ⁰ = Γ_m⁰ = 0;
ω, μ below two projects, T with no projects and β with no reviews are 0), trust weighting and
per-skill competency. Kept: A2 (the clip). Tests: `test_replication_*` in
`tests/algorithms/test_reputation_snapshot.py`, `test_weighted_mean_replication_ignores_trust`.

### Ambiguities A1–A13 (spec §9.0) and where each is tested (D91)

| # | Topic | Default | Phase | Test |
|---|---|---|---|---|
| A1 | Timeliness direction | Eq. 11 as written (faster = higher) | 6 | `test_A1_timeliness_direction` |
| A2 | Late work in Eq. 11 | ratio clipped to 1 | 6 | `test_A2_late_work_is_clipped` |
| A3 | Wrong team size in Eq. 17 | −∞ (paper prints −1, D9) | 7 | with `fitness.py` |
| A4 | Initial communication | Γ⁰ from verification | 6 | `test_A4_initial_communication_from_verification` |
| A5 | "ω + X = 1" | weights f, 1 − f sum to 1 | 6 | `test_A5_competency_weights_sum_to_one` |
| A6 | Older projects weigh more | α_x, α_e = 0.3 (< 0.5) | 6 | `test_A6_older_projects_weigh_more` |
| A7 | P in Eq. 17 | off (`fitness.include_performance`) | 7 | with `fitness.py` |
| A8 | External reviews | admin-verified only; none → β = λ | 6 | `test_A8_beta_uses_internal_reviews_only_without_verified_externals` |
| A9 | ω, μ for < 2 projects | ω⁰ from evidence; μ = 0.5 | 6 | `test_A9_omega_and_mu_below_two_projects` |
| A10 | Eq. 18 normaliser C | budget after fee | 7 | with `fitness.py` |
| A11 | Sign in Eq. 23 | ε = e^{−(q − q_max)θ2} | 10 | with the payment policy |
| A12 | Utility Eq. 24 | as written and U′ | 15 | with the experiments |
| A13 | Inertia in Eq. 14 | 1.0 with v_max clamp | 7 | with `bpso.py` |
