"""The Phase 6 gate's paper-alignment checker on a small synthetic repository (the tests
container has no `docs/`; the gate runs the real check on the checkout in `phase6_checks`):
it passes when aligned, and reports a missing row, a function that doesn't exist, a missing
status, an equation without a test and a missing document."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_paper_alignment import check

pytestmark = pytest.mark.unit

STATUS = ["exact", "exact with documented resolution (A1)", "DevSync extension"]


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    rows = "\n".join(
        f"| Eq. {n} thing | {STATUS[n % 3]} | `eq{n:02d}_thing` | `test_eq{n:02d}_thing` |"
        for n in range(1, 13)
    )
    (tmp_path / "docs" / "PAPER_ALIGNMENT.md").write_text(
        f"# Paper\n\n| Paper element | Status | Function | Tests |\n|---|---|---|---|\n{rows}\n",
        encoding="utf-8",
    )
    algo = tmp_path / "backend" / "app" / "algorithms"
    algo.mkdir(parents=True)
    funcs = "\n".join(f"def eq{n:02d}_thing():\n    pass\n" for n in range(1, 13))
    (algo / "reputation.py").write_text(funcs, encoding="utf-8")
    tests = tmp_path / "backend" / "tests" / "unit"
    tests.mkdir(parents=True)
    names = "\n".join(f"def test_eq{n:02d}_thing():\n    pass\n" for n in range(1, 13))
    (tests / "test_fake.py").write_text(names, encoding="utf-8")
    return tmp_path


def test_an_aligned_repository_passes(tmp_path: Path) -> None:
    assert check(_repo(tmp_path)) == []


def test_missing_row_function_status_and_test_are_reported(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    doc = root / "docs" / "PAPER_ALIGNMENT.md"
    lines = [ln for ln in doc.read_text(encoding="utf-8").splitlines() if "| Eq. 3 " not in ln]
    text = "\n".join(lines).replace("`eq05_thing`", "`eq05_nowhere`")
    text = text.replace("| Eq. 12 thing | exact |", "| Eq. 12 thing | unknown |")
    doc.write_text(text, encoding="utf-8")
    fake = root / "backend" / "tests" / "unit" / "test_fake.py"
    fake.write_text(fake.read_text(encoding="utf-8").replace("test_eq07_thing", "test_seven"),
                    encoding="utf-8")  # fmt: skip
    problems = "\n".join(check(root))
    assert "Eq. 3: no row" in problems
    assert "Eq. 5: function ['eq05_nowhere'] not found" in problems
    assert "Eq. 12: status must be one of" in problems
    assert "Eq. 7: no test name contains 'eq07'" in problems
    assert "Eq. 1:" not in problems


def test_missing_document_is_reported(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "docs" / "PAPER_ALIGNMENT.md").unlink()
    assert check(root) == ["docs/PAPER_ALIGNMENT.md is missing"]
