"""The paper-alignment checker (Phase 6, extended to Eq. 13–19 in Phase 7) on a small synthetic
repository (the tests container has no `docs/`; the gate runs the real check on the checkout):
it passes when aligned, and reports a missing row, a function that doesn't exist (in
`reputation.py` for Eq. 1–12, in `bpso.py`/`fitness.py` for Eq. 13–19), a missing status, an
equation without a test, a missing formation module and a missing document."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_paper_alignment import check

pytestmark = pytest.mark.unit

STATUS = ["exact", "exact with documented resolution (A1)", "DevSync extension"]


def _function_for(n: int) -> str:
    """Eq. 1–12 are `eqNN_…` in reputation.py; 13–16 live in bpso.py, 17–19 in fitness.py."""
    return f"eq{n:02d}_thing" if n <= 12 else (f"pso_step_{n}" if n <= 16 else f"fitness_{n}")


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    rows = "\n".join(
        f"| Eq. {n} thing | {STATUS[n % 3]} | `{_function_for(n)}` | `test_eq{n:02d}_thing` |"
        for n in range(1, 20)
    )
    (tmp_path / "docs" / "PAPER_ALIGNMENT.md").write_text(
        f"# Paper\n\n| Paper element | Status | Function | Tests |\n|---|---|---|---|\n{rows}\n",
        encoding="utf-8",
    )
    algo = tmp_path / "backend" / "app" / "algorithms"
    algo.mkdir(parents=True)
    funcs = "\n".join(f"def eq{n:02d}_thing():\n    pass\n" for n in range(1, 13))
    (algo / "reputation.py").write_text(funcs, encoding="utf-8")
    for module, eqs in (("bpso.py", range(13, 17)), ("fitness.py", range(17, 20))):
        body = "\n".join(f"def {_function_for(n)}():\n    pass\n" for n in eqs)
        (algo / module).write_text(body, encoding="utf-8")
    tests = tmp_path / "backend" / "tests" / "unit"
    tests.mkdir(parents=True)
    names = "\n".join(f"def test_eq{n:02d}_thing():\n    pass\n" for n in range(1, 20))
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


def test_formation_equations_need_a_function_in_bpso_or_fitness(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    doc = root / "docs" / "PAPER_ALIGNMENT.md"
    text = doc.read_text(encoding="utf-8")
    text = text.replace("`pso_step_14`", "`pso_step_nowhere`")  # not in bpso.py
    text = text.replace("`fitness_18`", "`eq01_thing`")  # exists, but in reputation.py
    text = "\n".join(ln for ln in text.splitlines() if "| Eq. 19 " not in ln)
    doc.write_text(text, encoding="utf-8")
    fake = root / "backend" / "tests" / "unit" / "test_fake.py"
    fake.write_text(fake.read_text(encoding="utf-8").replace("test_eq16_thing", "test_sixteen"),
                    encoding="utf-8")  # fmt: skip
    problems = "\n".join(check(root))
    assert "Eq. 14: function — not found in app/algorithms/bpso.py or fitness.py" in problems
    assert "Eq. 18: function — not found in app/algorithms/bpso.py or fitness.py" in problems
    assert "Eq. 19: no row" in problems
    assert "Eq. 16: no test name contains 'eq16'" in problems
    for fine in ("Eq. 13:", "Eq. 15:", "Eq. 17:"):
        assert fine not in problems


def test_a_formation_equation_named_in_fitness_is_found(tmp_path: Path) -> None:
    """Eq. 13–16 may name a fitness.py function too (the check looks in both modules)."""
    root = _repo(tmp_path)
    doc = root / "docs" / "PAPER_ALIGNMENT.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("`pso_step_13`", "`fitness_17`"), encoding="utf-8"
    )
    assert check(root) == []


@pytest.mark.parametrize("module", ["bpso.py", "fitness.py"])
def test_a_missing_formation_module_is_reported_not_a_crash(tmp_path: Path, module: str) -> None:
    root = _repo(tmp_path)
    (root / "backend" / "app" / "algorithms" / module).unlink()
    problems = check(root)
    assert f"app/algorithms/{module} is missing" in problems
    lost = range(13, 17) if module == "bpso.py" else range(17, 20)
    for eq in lost:
        assert any(p.startswith(f"Eq. {eq}: function") for p in problems), eq
