"""Paper alignment check (spec §17 Phase 6 gate: "docs/PAPER_ALIGNMENT.md lists all Eq. 1–12
with linked tests (script checks every equation id appears in a test name)").

For each [PCS] equation 1–12 it requires:
1. a row in `docs/PAPER_ALIGNMENT.md` whose first cell names it ("Eq. N"), whose function cell
   names a function that exists in `app/algorithms/reputation.py`, and whose status cell is one
   of the three labels §9.0 allows;
2. at least one test function anywhere under `backend/tests/` whose name contains the
   equation id `eqNN` (two digits), e.g. `test_eq01_omega_spec_example_2_1_1`.

Pure standard library; reads files only. Usage: `python scripts/check_paper_alignment.py [ROOT]`
(ROOT = repository root, default: two levels up). Exit 1 with one line per problem.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

EQUATIONS = range(1, 13)
STATUSES = ("exact", "exact with documented resolution", "DevSync extension")
ROW = re.compile(r"^\|\s*Eq\.\s*(\d+)\b(?P<rest>.*)\|\s*$")


def _functions(module: Path) -> set[str]:
    tree = ast.parse(module.read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}


def _test_names(tests: Path) -> set[str]:
    names: set[str] = set()
    for path in tests.rglob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
                "test_"
            ):
                names.add(node.name)
    return names


def check(root: Path) -> list[str]:
    """All problems found (empty when aligned). Pure apart from reading the files."""
    doc = root / "docs" / "PAPER_ALIGNMENT.md"
    module = root / "backend" / "app" / "algorithms" / "reputation.py"
    problems: list[str] = []
    if not doc.exists():
        return [f"{doc.relative_to(root)} is missing"]
    functions = _functions(module)
    tests = _test_names(root / "backend" / "tests")
    rows: dict[int, list[str]] = {}
    for line in doc.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line.strip())
        if m:
            row_cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.setdefault(int(m.group(1)), row_cells)
    for eq in EQUATIONS:
        eq_id = f"eq{eq:02d}"
        cells = rows.get(eq)
        if cells is None:
            problems.append(f"Eq. {eq}: no row in docs/PAPER_ALIGNMENT.md")
        else:
            text = " | ".join(cells)
            named = set(re.findall(r"\b(eq\d{2}_[a-z0-9_]+)\b", text))
            if not named or not named <= functions:
                problems.append(
                    f"Eq. {eq}: function {sorted(named) or '—'} not found in "
                    "app/algorithms/reputation.py"
                )
            if not any(s.lower() in text.lower() for s in STATUSES):
                problems.append(f"Eq. {eq}: status must be one of {STATUSES}")
        if not any(eq_id in name for name in tests):
            problems.append(f"Eq. {eq}: no test name contains '{eq_id}'")
    return problems


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    problems = check(root)
    for p in problems:
        print(f"check_paper_alignment: {p}")
    print(f"check_paper_alignment: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
