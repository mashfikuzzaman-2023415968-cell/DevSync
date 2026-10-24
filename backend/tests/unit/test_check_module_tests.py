"""The "every module has tests" checker and the generated TESTING.md table (spec §16.1).

Covers what the gate relies on: which signals count as a test, the allowlist rules (reason
required, stale entries, directory entries), import resolution on the frontend (aliases,
relative paths, index files, the router barrier) and the generated document section.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_module_tests import (
    DOC_END,
    DOC_START,
    backend_test_map,
    build_doc_section,
    check_side,
    feature_dirs_without_tests,
    frontend_test_map,
    load_allowlist,
    resolve_import,
    write_doc,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- backend mapping


@pytest.mark.parametrize(
    ("test_path", "source"),
    [
        ("tests/unit/test_x.py", "from app.services import widgets"),  # from-import
        ("tests/unit/test_x.py", "import app.services.widgets"),  # plain import
        ("tests/unit/test_x.py", '"""Drives services/widgets.py through the API."""'),  # mention
        ("tests/security/test_widgets.py", "nothing imported here"),  # named after the module
        ("tests/security/test_widgets_extra.py", "nothing imported here"),  # …with a suffix
    ],
)
def test_a_module_counts_as_tested(test_path: str, source: str) -> None:
    covered = backend_test_map(["app/services/widgets.py"], {test_path: source})
    assert covered == {"app/services/widgets.py": [test_path]}


@pytest.mark.parametrize(
    ("test_path", "source"),
    [
        ("tests/unit/test_other.py", "from app.services import projects"),
        ("tests/unit/test_widgetsomething.py", "x = 1"),  # not a word boundary
        ("tests/unit/test_rewidgets.py", "x = 1"),
    ],
)
def test_an_unrelated_test_does_not_count(test_path: str, source: str) -> None:
    assert backend_test_map(["app/services/widgets.py"], {test_path: source}) == {}


def test_a_broken_test_file_does_not_crash_the_scan() -> None:
    covered = backend_test_map(["app/services/widgets.py"], {"tests/x.py": "def ("})
    assert covered == {}


# --------------------------------------------------------------------------- allowlist


def write_allowlist(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "module_tests.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_allowlist_requires_a_reason(tmp_path: Path) -> None:
    path = write_allowlist(tmp_path, {"backend": {"app/x.py": "  "}, "frontend": {}})
    with pytest.raises(ValueError, match="need a reason"):
        load_allowlist(path)


def test_allowlist_reads_both_sides_and_tolerates_a_missing_file(tmp_path: Path) -> None:
    path = write_allowlist(
        tmp_path, {"_about": "notes", "backend": {"app/x.py": "why"}, "frontend": {}}
    )
    assert load_allowlist(path) == {"backend": {"app/x.py": "why"}, "frontend": {}}
    assert load_allowlist(tmp_path / "absent.json") == {"backend": {}, "frontend": {}}


def test_a_module_without_tests_or_an_entry_fails() -> None:
    failures, notes = check_side(["app/a.py", "app/b.py"], {"app/a.py": ["tests/t.py"]}, {})
    assert notes == []
    assert len(failures) == 1
    assert "app/b.py" in failures[0]


def test_an_allowlisted_module_passes_and_a_directory_entry_covers_its_modules() -> None:
    failures, notes = check_side(
        ["app/b.py", "frontend/src/features/admin/AdminApp.tsx"],
        {},
        {"app/b.py": "reason", "frontend/src/features/admin": "Phase 12"},
        areas=["frontend/src/features/admin"],
    )
    assert (failures, notes) == ([], [])


def test_a_stale_entry_fails_and_a_covered_one_is_only_reported() -> None:
    failures, notes = check_side(
        ["app/a.py"],
        {"app/a.py": ["tests/t.py"]},
        {"app/a.py": "reason", "app/gone.py": "reason"},
    )
    assert any("no longer exists" in f and "app/gone.py" in f for f in failures)
    assert any("now has tests" in n for n in notes)
    assert not any("app/a.py" in f for f in failures)


def test_a_feature_without_any_test_file_is_reported() -> None:
    modules = [
        PAGE,
        f"{FE}/features/account/SettingsPage.tsx",
    ]
    tests = [TEST]
    assert feature_dirs_without_tests(modules, tests) == ["account"]


# --------------------------------------------------------------------------- frontend mapping


FE = "frontend/src"
TEST = f"{FE}/features/bids/bids.test.tsx"
PAGE = f"{FE}/features/bids/BidPage.tsx"
ROW = f"{FE}/features/bids/parts/Row.tsx"
BUTTON = f"{FE}/components/ui/Button.tsx"

FILES = {
    PAGE,
    ROW,
    BUTTON,
    f"{FE}/lib/money.ts",
    f"{FE}/lib/index.ts",
}


@pytest.mark.parametrize(
    ("spec", "origin", "expected"),
    [
        ("@/lib/money", TEST, f"{FE}/lib/money.ts"),  # alias
        ("./BidPage", TEST, PAGE),  # sibling
        ("./parts/Row", PAGE, ROW),  # sub-folder
        ("../../components/ui/Button", PAGE, BUTTON),  # up and across
        ("@/lib", TEST, f"{FE}/lib/index.ts"),  # folder index
        ("react", TEST, None),  # a package
        ("@/lib/absent", TEST, None),  # nothing there
    ],
)
def test_import_resolution(spec: str, origin: str, expected: str | None) -> None:
    assert resolve_import(spec, origin, FILES) == expected


def test_a_test_reaches_what_its_page_renders() -> None:
    sources = {
        TEST: 'import BidPage from "./BidPage";',
        PAGE: 'import { Row } from "./parts/Row";',
        ROW: 'import { Button } from "@/components/ui/Button";',
        BUTTON: "export const Button = 1;",
    }
    modules = set(sources) - {TEST}
    covered = frontend_test_map(modules, sources, [TEST])
    assert set(covered) == modules
    direct = frontend_test_map(modules, sources, [TEST], direct_only=True)
    assert set(direct) == {PAGE}


def test_the_route_table_is_a_barrier() -> None:
    guards, router = f"{FE}/app/guards.test.tsx", f"{FE}/app/router.tsx"
    sources = {
        guards: 'import { router } from "./router";',
        router: 'const p = () => import("@/features/bids/BidPage");',
        PAGE: "export default 1;",
    }
    modules = set(sources) - {guards}
    reached = frontend_test_map(modules, sources, [guards], [router])
    # The router itself is covered by the test that imports it; the pages behind it are not.
    assert set(reached) == {router}


# --------------------------------------------------------------------------- the doc table

TWO_TESTS = "def test_one():\n    pass\ndef test_two():\n    pass\n"


def test_the_generated_section_lists_packages_areas_and_exceptions(tmp_path: Path) -> None:
    (tmp_path / "runs" / "gates").mkdir(parents=True)
    (tmp_path / "runs" / "gates" / "coverage-backend.json").write_text(
        json.dumps(
            {
                "files": {
                    "app/services/widgets.py": {
                        "summary": {"percent_covered": 90.0, "num_statements": 100}
                    },
                    "app/services/gadgets.py": {
                        "summary": {"percent_covered": 100.0, "num_statements": 100}
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    section = build_doc_section(
        tmp_path,
        {
            "app/services/widgets.py": ["tests/security/test_widgets.py"],
            "app/services/gadgets.py": [],
        },
        {"tests/security/test_widgets.py": TWO_TESTS},
        {PAGE: [TEST]},
        {PAGE: [TEST]},
        {TEST: "it('a', () => {});\ntest('b', () => {});\n"},
        {"backend": {"app/core/sprockets.py": "Phase 10"}, "frontend": {}},
    )
    assert section.startswith(DOC_START)
    assert section.endswith(DOC_END)
    assert "`app/services`" in section
    assert "`security/test_widgets.py` (2)" in section
    assert "95.0 %" in section  # statement-weighted over the two modules
    assert "| `frontend/src/features/bids` | 1 | `bids.test.tsx` (2) |" in section
    assert "| `app/core/sprockets.py` | Phase 10 |" in section


def test_without_a_coverage_report_the_column_is_a_dash(tmp_path: Path) -> None:
    section = build_doc_section(
        tmp_path, {"app/x.py": []}, {}, {}, {}, {}, {"backend": {}, "frontend": {}}
    )
    assert "| `app` | 1 | — | — |" in section


def test_write_doc_replaces_only_the_generated_section(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "TESTING.md"
    doc.parent.mkdir()
    doc.write_text(f"head\n{DOC_START}\nold\n{DOC_END}\ntail\n", encoding="utf-8")
    assert write_doc(tmp_path, f"{DOC_START}\nnew\n{DOC_END}") is True
    assert doc.read_text(encoding="utf-8") == f"head\n{DOC_START}\nnew\n{DOC_END}\ntail\n"
    # Writing the same section again changes nothing (the gate prints "unchanged").
    assert write_doc(tmp_path, f"{DOC_START}\nnew\n{DOC_END}") is False


def test_write_doc_needs_the_markers(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "TESTING.md"
    doc.parent.mkdir()
    doc.write_text("no markers here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="markers"):
        write_doc(tmp_path, f"{DOC_START}\nx\n{DOC_END}")
