"""Performance budget (spec §16.5 step 16): a reputation update over a 50-project history takes
less than 20 ms. Measured as the median of 21 runs after a warm-up, so one scheduler hiccup on a
loaded laptop can't fail it while a real slowdown still does."""

from __future__ import annotations

import statistics
import time
from decimal import Decimal

import pytest

from app.algorithms import reputation as r

pytestmark = pytest.mark.perf

BUDGET_MS = 20


def _history(n: int) -> list[r.ProjectRecord]:
    domains = ["FRONTEND", "BACKEND", "DATABASE", "TESTING", "DATA"]
    slots = tuple(Decimal(v) for v in ("0.5", "0.75", "1", "0.75", "1"))
    return [
        r.ProjectRecord(
            history_id=f"p{i}",
            domain=domains[i % len(domains)],
            client_key=f"c{i % 7}",
            t_days=10 + i % 25,
            deadline_days=30,
            gamma_comm=Decimal("0.72"),
            gamma_team=Decimal("0.64"),
            internal_slots=slots,
            external_slots=(Decimal("0.75"),) if i % 4 == 0 else (),
        )
        for i in range(n)
    ]


def test_reputation_for_50_project_history_under_20ms() -> None:
    history = _history(50)
    r.compute_snapshot(history)  # warm-up
    timings = []
    for _ in range(21):
        start = time.perf_counter()
        result = r.compute_snapshot(history)
        timings.append((time.perf_counter() - start) * 1000)
    assert result.snapshot.completed_projects == 50
    assert statistics.median(timings) < BUDGET_MS, f"median {statistics.median(timings):.1f} ms"
