# PAPER ALIGNMENT

Maps every [PCS] equation/algorithm to its DevSync function and test, labelled *exact*, *exact
with a documented resolution (A#, §9.0)* or *DevSync extension*. Filled as each phase builds it.

## Phase 5

| Paper element | Status | Function | Tests |
|---|---|---|---|
| Algorithm 1 — worker filtering ([PCS] §4.2) | exact, with the newcomer rule, relaxation and advancement as **DevSync extensions** (off in `pcs_replication`) | `app/algorithms/filtering.py::filter_bids` | `tests/algorithms/test_filtering.py` |
| Newcomer starting values (ours; A4, A9) | DevSync extension | `app/algorithms/reputation.py::newcomer_snapshot` | `tests/algorithms/test_reputation_newcomer.py` |
| Availability reservations (ours, §9.17) | DevSync extension | `app/algorithms/availability.py` | `tests/algorithms/test_availability.py` |

The full Eq. 1–12 reputation mapping arrives with the Phase 6 engine.
