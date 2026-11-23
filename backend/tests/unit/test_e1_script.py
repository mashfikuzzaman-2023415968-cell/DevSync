"""The E1 script: writes one row per solved instance, passes the §17 thresholds on a smoke run,
and refuses bad arguments."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.e1_bpso_vs_exact import FIELDS, main, run

pytestmark = pytest.mark.unit


def test_smoke_run_passes_and_writes_rows(tmp_path: Path) -> None:
    out = tmp_path / "e1.csv"
    assert main(["--instances", "20", "--out", str(out)]) == 0
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows
    assert tuple(rows[0]) == FIELDS
    assert {r["mode"] for r in rows} == {"devsync", "pcs_replication"}


def test_summary_numbers() -> None:
    optimal, mean_gap, n = run(10, None)
    assert n > 0
    assert 0 <= optimal <= 1
    assert mean_gap >= 0


@pytest.mark.parametrize("n", ["0", "10001", "x"])
def test_bad_instance_counts_are_refused(n: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--instances", n])
    assert exc.value.code == 2
