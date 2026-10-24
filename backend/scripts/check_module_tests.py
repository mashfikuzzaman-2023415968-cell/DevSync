"""Every module has tests (spec §16.1 "Unit testing rule", gate step 6).

Fails when a backend module under `backend/app/` or a frontend module under `frontend/src/`
has no test of its own, unless it is listed — with a reason — in `backend/tests/module_tests.json`.
The same scan writes the module → tests → coverage table of `docs/TESTING.md` (`--write-doc`),
so the supervisor's summary is refreshed by the gate instead of by hand.

How a module counts as tested:

* **Backend** — a test file (anything under `backend/tests/`) imports it (`import app.x.y`,
  `from app.x import y`), names it in its text (`app.x.y`, `x/y.py`: how the suites that drive a
  module through the API refer to it), or is named after it (`tests/**/test_<module>.py`, also
  `test_<module>_extra.py`), which is the convention §16.1 asks for. A test that uses a module
  path as *data* would count as naming it, so tests about this checker use invented names.
* **Frontend** — a unit test (`*.test.ts(x)`, `frontend/tests/**`) imports it, directly or
  through the modules it imports: a page's test exercises the components that page renders.
  A directory under `src/features/` must additionally own at least one test file, so a whole new
  feature cannot arrive untested.

Every entry in the allowlist needs a non-empty reason; an entry for a module that no longer
exists fails (it would hide a later module of the same name). Entries that have since gained
tests are reported, so they can be deleted.

Usage: `python scripts/check_module_tests.py [--write-doc] [REPO_ROOT]`; exits 1 on failures.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

BACKEND_DIRS = ("app",)
FRONTEND_EXT = (".ts", ".tsx")
FEATURES_DIR = "src/features"
# The route table imports every page (lazily); following its imports would mark the whole
# application as tested because one test renders a guarded route.
FRONTEND_BARRIERS = ("frontend/src/app/router.tsx", "frontend/src/app/App.tsx")
DOC_START = "<!-- module-tests:start -->"
DOC_END = "<!-- module-tests:end -->"
TEST_FUNCTION = re.compile(r"^\s*(?:async\s+)?def (test_\w+)", re.MULTILINE)
TS_TEST_FUNCTION = re.compile(r"^\s*(?:it|test)(?:\.\w+)?\s*\(", re.MULTILINE)
IMPORT_SPEC = re.compile(r"""(?:from|import)\s*\(?\s*['"]([^'"]+)['"]""")


# --------------------------------------------------------------------------- allowlist


def load_allowlist(path: Path) -> dict[str, dict[str, str]]:
    """Return {"backend": {module: reason}, "frontend": {module: reason}}."""
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    result: dict[str, dict[str, str]] = {"backend": {}, "frontend": {}}
    for side in result:
        entries = (data or {}).get(side) or {}
        missing = [m for m, reason in entries.items() if not str(reason or "").strip()]
        if missing:
            raise ValueError(f"{path.name}: {side} entries need a reason: {sorted(missing)}")
        result[side] = {str(m): str(reason).strip() for m, reason in entries.items()}
    return result


# --------------------------------------------------------------------------- backend


def backend_test_map(modules: Iterable[str], test_sources: dict[str, str]) -> dict[str, list[str]]:
    """{module path → test files that cover it}, by import, mention or name (pure)."""
    covered: dict[str, list[str]] = {}
    for module in modules:
        dotted = module.removesuffix(".py").replace("/", ".")
        mentioned = module.removeprefix("app/")
        stem = dotted.rsplit(".", 1)[-1]
        named = re.compile(rf"(^|_){re.escape(stem)}(_|$)")
        for test_path, source in sorted(test_sources.items()):
            test_stem = Path(test_path).stem
            hit = (
                dotted in _imported(source)
                or dotted in source
                or mentioned in source
                or (test_stem.startswith("test_") and named.search(test_stem.removeprefix("test_")))
            )
            if hit:
                covered.setdefault(module, []).append(test_path)
    return covered


def _imported(source: str) -> set[str]:
    """Module names imported by a Python source (`import a.b`, `from a import b`)."""
    names: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def backend_modules(backend: Path) -> list[str]:
    """Importable modules under `app/`, relative to the backend root (`__init__.py` skipped)."""
    found: list[str] = []
    for top in BACKEND_DIRS:
        for path in sorted((backend / top).rglob("*.py")):
            if path.name != "__init__.py":
                found.append(path.relative_to(backend).as_posix())
    return found


def backend_test_sources(backend: Path) -> dict[str, str]:
    return {
        path.relative_to(backend).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((backend / "tests").rglob("*.py"))
        if path.name != "__init__.py"
    }


# --------------------------------------------------------------------------- frontend


def _normalise(path: str) -> str:
    """Collapse '.' and '..' segments of a POSIX path (no filesystem access)."""
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == ".." and parts and parts[-1] != "..":
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def resolve_import(spec: str, origin: str, files: set[str]) -> str | None:
    """Resolve an import specifier to a repository path ('@/x' and relative paths only)."""
    if spec.startswith("@/"):
        base = _normalise(f"frontend/src/{spec[2:]}")
    elif spec.startswith("."):
        base = _normalise(f"{Path(origin).parent.as_posix()}/{spec}")
    else:
        return None  # a package from node_modules
    candidates = [base, *(f"{base}{ext}" for ext in FRONTEND_EXT)]
    candidates += [f"{base}/index{ext}" for ext in FRONTEND_EXT]
    for candidate in candidates:
        if candidate in files:
            return candidate
    return None


def frontend_test_map(
    modules: set[str],
    sources: dict[str, str],
    tests: Iterable[str],
    barriers: Iterable[str] = (),
    *,
    direct_only: bool = False,
) -> dict[str, list[str]]:
    """{module → unit tests that reach it}, following imports transitively (pure).

    With `direct_only`, only the modules a test imports itself are mapped — that is what the
    generated table in docs/TESTING.md shows, so a page's test is not listed against every
    component in the application.

    `barriers` are modules whose own imports are not followed: the route table imports every
    page, so without it one test of the router would mark the whole application as tested.
    A barrier still counts as covered by the test that imports it.
    """
    files = set(sources)
    stop = set(barriers)
    covered: dict[str, list[str]] = {}
    for test in sorted(tests):
        seen: set[str] = set()
        stack = [test]
        while stack:
            current = stack.pop()
            if current in seen or current not in sources:
                continue
            seen.add(current)
            if current in stop and current != test:
                continue
            for spec in IMPORT_SPEC.findall(sources[current]):
                target = resolve_import(spec, current, files)
                if target is None:
                    continue
                if target in modules and test not in covered.get(target, []):
                    covered.setdefault(target, []).append(test)
                if not direct_only:
                    stack.append(target)
    return covered


def is_frontend_test(path: str) -> bool:
    return ".test." in Path(path).name or path.startswith("frontend/tests/")


def frontend_sources(frontend: Path, repo: Path) -> dict[str, str]:
    """All TypeScript sources under `src/` and `tests/`, keyed by repository path."""
    sources: dict[str, str] = {}
    for folder in ("src", "tests"):
        for path in sorted((frontend / folder).rglob("*")):
            if path.suffix in FRONTEND_EXT and not path.name.endswith(".d.ts"):
                sources[path.relative_to(repo).as_posix()] = path.read_text(encoding="utf-8")
    return sources


# --------------------------------------------------------------------------- checks


def feature_dirs_without_tests(modules: Iterable[str], tests: Iterable[str]) -> list[str]:
    """Feature areas (`src/features/<area>`) that own no test file at all."""
    areas = {
        m.split("/")[3] for m in modules if f"/{FEATURES_DIR}/" in f"/{m}" and m.count("/") > 3
    }
    with_tests = {
        t.split("/")[3] for t in tests if f"/{FEATURES_DIR}/" in f"/{t}" and t.count("/") > 3
    }
    return sorted(areas - with_tests)


def _allowed(module: str, allowed: dict[str, str]) -> bool:
    """True when the module itself, or the directory it belongs to, is listed with a reason."""
    return module in allowed or any(
        module.startswith(f"{key}/") for key in allowed if not key.endswith((".py", ".ts", ".tsx"))
    )


def check_side(
    modules: Iterable[str],
    covered: dict[str, list[str]],
    allowed: dict[str, str],
    areas: Iterable[str] = (),
) -> tuple[list[str], list[str]]:
    """(failures, notes) for one side of the repository. `areas` are directory keys the
    allowlist may carry (a whole feature area whose phase has not arrived yet)."""
    modules = list(modules)
    known = {*modules, *areas}
    failures = [
        f"{module}: no test refers to it"
        " (add a test, or an entry with a reason in module_tests.json)"
        for module in modules
        if module not in covered and not _allowed(module, allowed)
    ]
    failures += [
        f"{module}: listed in module_tests.json but the module no longer exists"
        for module in allowed
        if module not in known
    ]
    notes = [
        f"{module}: now has tests ({', '.join(covered[module][:3])}); its allowlist entry can go"
        for module in allowed
        if module in covered
    ]
    return failures, notes


# --------------------------------------------------------------------------- the doc table


def _count_python_tests(source: str) -> int:
    return len(TEST_FUNCTION.findall(source))


def _count_ts_tests(source: str) -> int:
    return len(TS_TEST_FUNCTION.findall(source))


def _coverage(repo: Path) -> dict[str, tuple[float, int]]:
    """{backend module → (percent covered incl. branches, statements)} from the gate's report."""
    report = repo / "runs" / "gates" / "coverage-backend.json"
    if not report.exists():
        return {}
    data = json.loads(report.read_text(encoding="utf-8"))
    return {
        path: (
            float(info["summary"]["percent_covered"]),
            int(info["summary"]["num_statements"]),
        )
        for path, info in data.get("files", {}).items()
    }


def _directory(module: str) -> str:
    return str(Path(module).parent).replace("\\", "/")


def build_doc_section(  # noqa: PLR0917 - one argument per input of the generated table
    repo: Path,
    backend_covered: dict[str, list[str]],
    backend_sources: dict[str, str],
    frontend_covered: dict[str, list[str]],
    frontend_direct: dict[str, list[str]],
    frontend_sources: dict[str, str],
    allowlist: dict[str, dict[str, str]],
) -> str:
    """The generated part of docs/TESTING.md (kept between the markers)."""
    coverage = _coverage(repo)
    lines = [
        DOC_START,
        "",
        "<!-- Generated by backend/scripts/check_module_tests.py at every gate; do not edit. -->",
        "",
        "### Backend (`backend/app` → `backend/tests`)",
        "",
        "Coverage is line + branch coverage of the latest gate run",
        "(`runs/gates/coverage-backend.json`), weighted by statements; the busiest test files",
        "of each package are listed.",
        "",
        "| Package | Modules | Tests (files, static count) | Coverage |",
        "|---|---|---|---|",
    ]
    packages: dict[str, list[str]] = {}
    for module in sorted(backend_covered) + [
        m for m in sorted(allowlist["backend"]) if m not in backend_covered
    ]:
        packages.setdefault(_directory(module), []).append(module)
    for package, modules in sorted(packages.items()):
        tests: dict[str, int] = {}
        for module in modules:
            for test in backend_covered.get(module, []):
                tests[test] = _count_python_tests(backend_sources.get(test, ""))
        covered_pct = _package_coverage(modules, coverage)
        busiest = sorted(
            ((t, n) for t, n in tests.items() if n), key=lambda item: (-item[1], item[0])
        )
        listed = ", ".join(
            f"`{Path(t).relative_to('tests').as_posix()}` ({n})" for t, n in busiest[:6]
        )
        if len(busiest) > 6:
            listed += f", … ({len(busiest) - 6} more)"
        lines.append(f"| `{package}` | {len(modules)} | {listed or '—'} | {covered_pct} |")
    lines += [
        "",
        "### Frontend (`frontend/src` → Vitest)",
        "",
        "A page's test exercises the components it renders, so a module counts as tested when",
        "a unit test reaches it through its imports. Per-file frontend coverage is not kept",
        "between runs (`frontend/coverage/` is regenerated by the gate); the gate enforces the",
        "phase threshold on statements, branches, functions and lines.",
        "",
        "| Area | Modules reached | Tests that import them (static count) |",
        "|---|---|---|",
    ]
    areas: dict[str, set[str]] = {}
    tests_by_area: dict[str, set[str]] = {}
    for module, tests_list in sorted(frontend_covered.items()):
        parts = module.split("/")
        # One row per feature (src/features/bids), per folder elsewhere (src/lib).
        area = "/".join(parts[:4]) if parts[2:3] == ["features"] else "/".join(parts[:3])
        areas.setdefault(area, set()).add(module)
        tests_by_area.setdefault(area, set()).update(frontend_direct.get(module, tests_list))
    for area, modules_set in sorted(areas.items()):
        counted = sorted(
            (
                (t, _count_ts_tests(frontend_sources.get(t, "")))
                for t in tests_by_area.get(area, set())
            ),
            key=lambda item: (-item[1], item[0]),
        )
        listed = ", ".join(f"`{Path(t).name}` ({n})" for t, n in counted[:6])
        if len(counted) > 6:
            listed += f", … ({len(counted) - 6} more)"
        lines.append(f"| `{area}` | {len(modules_set)} | {listed or '—'} |")
    lines += [
        "",
        "### Modules without tests of their own (reviewed exceptions)",
        "",
        "From `backend/tests/module_tests.json`; the gate fails on any module that is neither",
        "covered nor listed here.",
        "",
        "| Module | Why |",
        "|---|---|",
    ]
    for side in ("backend", "frontend"):
        for module, reason in sorted(allowlist[side].items()):
            lines.append(f"| `{module}` | {reason} |")
    lines += ["", DOC_END]
    return "\n".join(lines)


def _package_coverage(modules: list[str], coverage: dict[str, tuple[float, int]]) -> str:
    """Statement-weighted coverage of a package, or '—' when the gate has no report yet."""
    known = [coverage[m] for m in modules if m in coverage]
    total = sum(statements for _pct, statements in known)
    if not known or total == 0:
        return "—"
    weighted = sum(pct * statements for pct, statements in known) / total
    return f"{weighted:.1f} %"


def write_doc(repo: Path, section: str) -> bool:
    """Replace the generated section of docs/TESTING.md; True when the file changed."""
    doc = repo / "docs" / "TESTING.md"
    text = doc.read_text(encoding="utf-8")
    if DOC_START not in text or DOC_END not in text:
        raise ValueError(f"{doc.name} has no {DOC_START} / {DOC_END} markers")
    head, rest = text.split(DOC_START, 1)
    _old, tail = rest.split(DOC_END, 1)
    updated = head + section + tail
    if updated == text:
        return False
    doc.write_text(updated, encoding="utf-8")
    return True


# --------------------------------------------------------------------------- CLI


def main(argv: list[str]) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?", default=None)
    parser.add_argument("--write-doc", action="store_true", help="refresh docs/TESTING.md")
    args = parser.parse_args(argv[1:])
    repo = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parents[2]
    backend, frontend = repo / "backend", repo / "frontend"

    allowlist = load_allowlist(backend / "tests" / "module_tests.json")
    modules = backend_modules(backend)
    sources = backend_test_sources(backend)
    backend_covered = backend_test_map(modules, sources)
    failures, notes = check_side(modules, backend_covered, allowlist["backend"])

    fe_sources = frontend_sources(frontend, repo)
    fe_modules = {
        path
        for path in fe_sources
        if path.startswith("frontend/src/") and not is_frontend_test(path) and "/test/" not in path
    }
    fe_tests = [path for path in fe_sources if is_frontend_test(path)]
    frontend_covered = frontend_test_map(fe_modules, fe_sources, fe_tests, FRONTEND_BARRIERS)
    fe_areas = {"/".join(m.split("/")[:4]) for m in fe_modules if f"/{FEATURES_DIR}/" in f"/{m}"}
    fe_failures, fe_notes = check_side(
        sorted(fe_modules), frontend_covered, allowlist["frontend"], fe_areas
    )
    failures += fe_failures
    notes += fe_notes
    failures += [
        f"frontend/{FEATURES_DIR}/{area}: the feature has no test file of its own"
        for area in feature_dirs_without_tests(fe_modules, fe_tests)
        if f"frontend/{FEATURES_DIR}/{area}" not in allowlist["frontend"]
    ]

    for note in notes:
        print(f"note: {note}")
    for failure in failures:
        print(failure)
    if args.write_doc:
        direct = frontend_test_map(
            fe_modules, fe_sources, fe_tests, FRONTEND_BARRIERS, direct_only=True
        )
        section = build_doc_section(
            repo, backend_covered, sources, frontend_covered, direct, fe_sources, allowlist
        )
        changed = write_doc(repo, section)
        print(f"check_module_tests: docs/TESTING.md {'updated' if changed else 'unchanged'}")
    print(
        f"check_module_tests: {len(modules)} backend + {len(fe_modules)} frontend modules, "
        f"{len(failures)} without tests"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
