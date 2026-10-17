"""The forbidden-pattern scanner detects each rule and honours `forbidden-ok` (spec §16.7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_forbidden import scan, scan_python, scan_ts

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("x = eval('1')", "eval("),
        ("exec('x=1')", "exec("),
        ("import pickle", "pickle/marshal/shelve"),
        ("import yaml\nyaml.load(s)", "yaml.load (use safe_load)"),
        ("subprocess.run('ls', shell=True)", "shell=True"),
        ("os.system('ls')", "os.system / os.popen"),
        ("tempfile.mktemp()", "tempfile.mktemp"),
        ("httpx.get(u, verify=False)", "httpx verify=False"),
        ("app.add_middleware(C, allow_origins=['*'])", "CORS allow all"),
        ("v = float(amount_paisa)", "float/'/ 100' on paisa"),
        ("v = amount_paisa / 100", "float/'/ 100' on paisa"),
        ("print('x')", "print( in app/"),
        ("assert x", "assert in app/"),
        ("if token == other: pass", "==/!= on secret-like 'token' (use hmac.compare_digest)"),
        ("conn.execute(text('SELECT 1'))", "raw SQL text( outside alembic/ and app/reports/"),
        ("log.info('x', password=p)", "logging of secret-named field 'password'"),
    ],
)
def test_python_rules(source: str, rule: str) -> None:
    hits = scan_python("backend/app/services/x.py", source)
    assert rule in [r for _, r in hits]


def test_sql_column_comparisons_are_not_flagged() -> None:
    src = "stmt = select(T).where(Session.token_hash == token_hash)"
    assert scan_python("backend/app/repositories/x.py", src) == []


def test_money_files_reject_float_and_math() -> None:
    hits = [
        r
        for _, r in scan_python(
            "backend/app/core/money.py", "x = float('1')\nimport math\nmath.exp(1)"
        )
    ]
    assert "float/math in money code (use Decimal)" in hits


def test_security_modules_reject_random_and_todo() -> None:
    src = "import random\nx = random.random()  # TODO later"
    hits = [r for _, r in scan_python("backend/app/core/security.py", src)]
    assert "random. in security module (use secrets)" in hits
    assert "TODO/FIXME in security-critical module" in hits


def test_raw_sql_allowed_in_reports() -> None:
    assert scan_python("backend/app/reports/r.py", "text('SELECT 1')") == []


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("<div dangerouslySetInnerHTML={x} />", "dangerouslySetInnerHTML"),
        ("el.innerHTML = s", "innerHTML/outerHTML"),
        ("el.insertAdjacentHTML('x', s)", "insertAdjacentHTML"),
        ("document.write(s)", "document.write"),
        ("eval(code)", "eval("),
        ("new Function('return 1')", "new Function("),
        ("setTimeout('alert(1)', 1)", "string setTimeout"),
        ("localStorage.setItem('session_token', t)", "token/PII in web storage"),
        ('<a href="/x" target="_blank">x</a>', "target=_blank without noopener"),
        ("fetch('https://evil.example/x')", "external URL literal"),
    ],
)
def test_ts_rules(source: str, rule: str) -> None:
    assert rule in [r for _, r in scan_ts(source)]


def test_safe_ts_is_clean() -> None:
    src = (
        '<a href="/x" target="_blank" rel="noopener noreferrer">x</a>\n'
        'localStorage.setItem("theme", t)'
    )
    assert scan_ts(src) == []


def test_forbidden_ok_marks_exception_as_allowed(tmp_path: Path) -> None:
    app = tmp_path / "backend" / "app"
    app.mkdir(parents=True)
    (app / "a.py").write_text("print('x')  # forbidden-ok: CLI banner\nprint('y')\n")
    findings = scan(tmp_path)
    assert [(f.line, f.allowed) for f in findings] == [(1, True), (2, False)]


def test_repo_rules_and_env_files(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET_KEY=x\n")
    (tmp_path / ".env.example").write_text("SECRET_KEY=\n")
    (tmp_path / "notes.md").write_text("-----BEGIN PRIVATE KEY-----\n")
    rules = {f.rule for f in scan(tmp_path)}
    assert "committed .env file" in rules
    assert "private key" in rules


def test_tests_are_excluded(tmp_path: Path) -> None:
    t = tmp_path / "backend" / "tests"
    t.mkdir(parents=True)
    (t / "test_a.py").write_text("assert eval('1') == 1\n")
    assert scan(tmp_path) == []
