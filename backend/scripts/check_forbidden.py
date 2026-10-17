"""Forbidden-pattern scanner (spec §16.7).

Usage: `python scripts/check_forbidden.py [REPO_ROOT]` — exits 1 if any finding.

Python files are checked with the AST where precision matters (calls, comparisons,
`assert`, floats in money code) and with line regexes for the rest. TS/JS files
use line regexes. A finding is allowed only with a same-line
`# forbidden-ok: <reason>` / `// forbidden-ok: <reason>` comment; allowed
exceptions are listed in the report so the gate shows them.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "coverage",
    "playwright-report",
    "test-results",
    "runs",
    ".claude",
}
OK_MARK = re.compile(r"(#|//)\s*forbidden-ok:\s*\S")

SECRET_NAME = re.compile(r"(token|secret|digest|hash|otp|signature|csrf)", re.IGNORECASE)
LOGGED_SECRET_NAME = re.compile(r"^(password|token|secret|otp|session)", re.IGNORECASE)
MONEY_STRICT_FILES = (
    "app/core/money.py",
    "app/algorithms/payment_policy.py",
    "app/algorithms/splits.py",
)
SECURITY_MODULES = (
    "app/core/security.py",
    "app/core/sessions.py",
    "app/core/csrf.py",
    "app/core/authz.py",
    "app/core/ratelimit.py",
    "app/core/redirects.py",
    "app/core/money.py",
    "app/uploads/",
    "app/services/ledger",
)
RAW_SQL_ALLOWED = ("alembic/", "app/reports/")

# Line regexes for Python (outside tests).
PY_LINE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "pickle/marshal/shelve",
        re.compile(r"\bimport\s+(pickle|marshal|shelve)\b|\bfrom\s+(pickle|marshal|shelve)\b"),
    ),
    ("yaml.load (use safe_load)", re.compile(r"\byaml\.load\(")),
    ("shell=True", re.compile(r"shell\s*=\s*True")),
    ("os.system / os.popen", re.compile(r"\bos\.(system|popen)\(")),
    ("tempfile.mktemp", re.compile(r"\btempfile\.mktemp\(")),
    ("httpx verify=False", re.compile(r"verify\s*=\s*False")),
    ("CORS allow all", re.compile(r"allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\]")),
    ("float/'/ 100' on paisa", re.compile(r"float\(\s*\w*_paisa\b|\w+_paisa\s*/\s*100\b")),
]

TS_LINE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("dangerouslySetInnerHTML", re.compile(r"dangerouslySetInnerHTML")),
    ("innerHTML/outerHTML", re.compile(r"\.(innerHTML|outerHTML)\b")),
    ("insertAdjacentHTML", re.compile(r"insertAdjacentHTML")),
    ("document.write", re.compile(r"document\.write\(")),
    ("eval(", re.compile(r"(?<![\w.])eval\(")),
    ("new Function(", re.compile(r"new\s+Function\(")),
    ("string setTimeout", re.compile(r"setTimeout\(\s*[\"'`]")),
    (
        "token/PII in web storage",
        re.compile(
            r"(localStorage|sessionStorage)\.setItem\(\s*[\"'`][^\"'`]*(token|session|password|email|phone)",
            re.IGNORECASE,
        ),
    ),
    (
        "target=_blank without noopener",
        re.compile(r"target=[\"']_blank[\"'](?![^>]*rel=[\"'][^\"']*noopener)"),
    ),
    (
        "external URL literal",
        re.compile(
            r"[\"'`]https?://(?!localhost|127\.0\.0\.1|github\.com|www\.w3\.org|schemas\.)[^\"'`\s]+"
        ),
    ),
]

REPO_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("private key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]


@dataclass(frozen=True)
class Finding:
    """One rule violation (or allowed exception)."""

    path: str
    line: int
    rule: str
    allowed: bool

    def render(self) -> str:
        tag = "allowed" if self.allowed else "FORBIDDEN"
        return f"{tag}: {self.path}:{self.line}: {self.rule}"


def _is_test_path(rel: str) -> bool:
    return (
        "/tests/" in f"/{rel}"
        or rel.startswith(("e2e/", "frontend/tests/"))
        or ".test." in rel
        or ".spec." in rel
    )


class _PyVisitor(ast.NodeVisitor):
    """AST checks that regexes can't do reliably."""

    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.hits: list[tuple[int, str]] = []
        app_rel = rel.removeprefix("backend/")
        self.in_app = app_rel.startswith("app/")
        self.money_strict = app_rel.startswith(MONEY_STRICT_FILES) or app_rel.startswith(
            "app/services/ledger"
        )
        self.security_module = app_rel.startswith(SECURITY_MODULES)
        self.raw_sql_ok = app_rel.startswith(RAW_SQL_ALLOWED)

    def _name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._name(node.value)}.{node.attr}"
        return ""

    def visit_Call(self, node: ast.Call) -> None:
        name = self._name(node.func)
        if name in {"eval", "exec"}:
            self.hits.append((node.lineno, f"{name}("))
        if self.in_app and name == "print":
            self.hits.append((node.lineno, "print( in app/"))
        if self.in_app and name in {"text", "sqlalchemy.text", "sa.text"} and not self.raw_sql_ok:
            self.hits.append((node.lineno, "raw SQL text( outside alembic/ and app/reports/"))
        if self.money_strict and (name == "float" or name.startswith("math.")):
            self.hits.append((node.lineno, "float/math in money code (use Decimal)"))
        if self.security_module and name.startswith("random."):
            self.hits.append((node.lineno, "random. in security module (use secrets)"))
        if name.split(".")[-1] in {"info", "debug", "warning", "error", "exception", "critical"}:
            for kw in node.keywords:
                if kw.arg and LOGGED_SECRET_NAME.match(kw.arg):
                    self.hits.append((node.lineno, f"logging of secret-named field '{kw.arg}'"))
            for arg in node.args:
                if isinstance(arg, ast.Name) and LOGGED_SECRET_NAME.match(arg.id):
                    self.hits.append((node.lineno, f"logging of secret-named variable '{arg.id}'"))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops):
            for side in [node.left, *node.comparators]:
                name = self._name(side).split(".")[-1]
                if name and SECRET_NAME.search(name):
                    self.hits.append(
                        (node.lineno, f"==/!= on secret-like '{name}' (use hmac.compare_digest)")
                    )
                    break
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        if self.in_app:
            self.hits.append((node.lineno, "assert in app/"))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if self.money_strict and node.id == "float":
            self.hits.append((node.lineno, "float in money code (use Decimal)"))
        self.generic_visit(node)


def _iter_files(root: Path) -> list[Path]:
    """Files git would commit (tracked + untracked, minus .gitignore'd); else a filesystem walk.

    Ignored local files such as `.env` and dev certificates are not repository content,
    so they are skipped when git is available (gitleaks covers the history separately).
    """
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            check=True,
        ).stdout
        rels = [r for r in out.decode("utf-8").split("\0") if r]
        return [
            root / r
            for r in rels
            if not any(part in EXCLUDED_DIRS for part in Path(r).parts) and (root / r).is_file()
        ]
    except (OSError, subprocess.CalledProcessError):
        files: list[Path] = []
        for path in root.rglob("*"):
            if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
                continue
            if path.is_file():
                files.append(path)
        return files


def scan_python(rel: str, source: str) -> list[tuple[int, str]]:
    """Return (line, rule) hits for one Python file."""
    hits: list[tuple[int, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(exc.lineno or 0, "syntax error")]
    visitor = _PyVisitor(rel)
    visitor.visit(tree)
    hits.extend(visitor.hits)
    lines = source.splitlines()
    for i, line in enumerate(lines, start=1):
        for rule, pattern in PY_LINE_RULES:
            if pattern.search(line):
                hits.append((i, rule))
        if visitor.security_module and re.search(r"\b(TODO|FIXME)\b", line):
            hits.append((i, "TODO/FIXME in security-critical module"))
    return hits


def scan_ts(source: str) -> list[tuple[int, str]]:
    """Return (line, rule) hits for one TS/JS file."""
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(source.splitlines(), start=1):
        for rule, pattern in TS_LINE_RULES:
            if pattern.search(line):
                hits.append((i, rule))
    return hits


def scan(root: Path) -> list[Finding]:
    """Scan the repository rooted at `root`."""
    findings: list[Finding] = []
    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        name = path.name
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            findings.append(Finding(rel, 0, "committed .env file", allowed=False))
            continue
        if rel.startswith("data/uploads/") or (
            "/uploads/" in rel and not rel.startswith("backend/app/")
        ):
            findings.append(Finding(rel, 0, "committed upload", allowed=False))
            continue
        if path.suffix in {
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".woff",
            ".woff2",
            ".ico",
            ".lock",
        }:
            continue
        if path.stat().st_size > 2_000_000:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines = source.splitlines()
        hits: list[tuple[int, str]] = []
        if rel.endswith("check_forbidden.py") or rel.endswith("test_check_forbidden.py"):
            pass  # the scanner and its tests necessarily contain the patterns
        elif path.suffix == ".py" and not _is_test_path(rel):
            hits.extend(scan_python(rel, source))
        elif path.suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs"} and not _is_test_path(rel):
            hits.extend(scan_ts(source))
        if not rel.endswith(("check_forbidden.py", "test_check_forbidden.py")):
            for i, line in enumerate(lines, start=1):
                for rule, pattern in REPO_RULES:
                    if pattern.search(line):
                        hits.append((i, rule))
        for line_no, rule in hits:
            text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
            findings.append(Finding(rel, line_no, rule, allowed=bool(OK_MARK.search(text))))
    return sorted(findings, key=lambda f: (f.path, f.line))


def main(argv: list[str]) -> int:
    """CLI entry point."""
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[2]
    findings = scan(root)
    for f in findings:
        print(f.render())
    bad = [f for f in findings if not f.allowed]
    allowed = len(findings) - len(bad)
    print(f"check_forbidden: {len(bad)} forbidden, {allowed} allowed exception(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
