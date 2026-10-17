"""Layer checker, RLS coverage logic and OpenAPI linter (spec §5.2, §14.15, §10.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from scripts.check_layers import check_file
from scripts.check_openapi import lint
from scripts.check_rls import find_unprotected, load_exempt

pytestmark = pytest.mark.unit


def write(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return path


@pytest.mark.parametrize(
    ("rel", "source", "fragment"),
    [
        ("app/api/v1/x.py", "from app.repositories import users", "must not import"),
        ("app/api/v1/x.py", "import app.models", "must not import"),
        ("app/repositories/x.py", "from app.services import y", "must not import"),
        ("app/algorithms/x.py", "from app.db import session", "must not import"),
        ("app/algorithms/x.py", "import sqlalchemy", "pure algorithms must not import"),
        ("app/algorithms/x.py", "import datetime\nx = datetime.datetime.now()", "clock"),
    ],
)
def test_layer_violations_are_reported(
    tmp_path: Path, rel: str, source: str, fragment: str
) -> None:
    errors = check_file(write(tmp_path, rel, source), tmp_path)
    assert any(fragment in e for e in errors), errors


def test_allowed_imports_pass(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "app/services/x.py",
        "from app.repositories import a\nfrom app.algorithms import b",
    )
    assert check_file(path, tmp_path) == []


def test_rls_unprotected_tables_are_found() -> None:
    rows = [
        ("users", True, True),
        ("skills", False, False),
        ("bids", True, False),
        ("alembic_version", False, False),
    ]
    assert find_unprotected(rows, {"skills": "public taxonomy"}) == ["bids"]


def test_rls_exempt_requires_reason(tmp_path: Path) -> None:
    f = tmp_path / "e.yml"
    f.write_text("tables:\n  skills: ''\n")
    with pytest.raises(ValueError, match="reason"):
        load_exempt(f)
    f.write_text("tables:\n  skills: public taxonomy\n")
    assert load_exempt(f) == {"skills": "public taxonomy"}
    assert load_exempt(tmp_path / "missing.yml") == {}


def op(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "summary": "Do it",
        "responses": {
            "200": {"content": {"application/json": {"example": {"ok": True}}}},
            "401": {},
            "403": {},
            "404": {},
        },
    }
    base.update(overrides)
    return base


def test_openapi_lint_accepts_complete_operation() -> None:
    assert lint({"paths": {"/api/v1/x": {"get": op()}}}) == []


def test_openapi_lint_reports_gaps() -> None:
    bad = op(summary="", responses={"200": {"content": {"application/json": {}}}})
    bad["requestBody"] = {"content": {"application/json": {"schema": {"type": "object"}}}}
    problems = lint({"paths": {"/api/v1/x": {"post": bad}}})
    text = "\n".join(problems)
    assert "missing summary" in text
    assert "no example" not in text  # empty content has nothing to exemplify
    assert "missing declared responses" in text
    assert "untyped object schema" in text


def test_openapi_lint_public_operations_need_no_auth_errors() -> None:
    public = {
        "summary": "Live",
        "responses": {"200": {"content": {"application/json": {"example": {}}}}},
    }
    assert lint({"paths": {"/api/v1/health": {"get": public}}}) == []
