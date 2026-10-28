"""Execute every code question of the bank (role assessment spec §13.3, rule 1).

Each question marked `check: execution` has a check file `<skill>/<question_id>.py` (dashes as
underscores) defining `check(ctx, q)`. The check runs the snippet for real — Python with this
interpreter, JavaScript with Node, SQL against a throwaway PostgreSQL — and asserts that the
marked option is right and every other option is wrong. `make question-checks` starts the
database and runs this script; any failure exits non-zero, and the bank build refuses to approve
a code question whose check hasn't passed.

    QCHECK_DSN=postgresql://… python scripts/question_checks/run_checks.py \
        [--only ID …] [--json OUT]

`ctx` offers:
- `ctx.python(code) -> str`  stdout of `python -c code` (stderr included on failure)
- `ctx.node(code, module=False) -> str`  stdout of `node -e code`
- `ctx.sql(script) -> list[tuple]`  runs the script in a fresh schema; rows of the last statement
- `ctx.expect_only(q, actual)`  asserts `q["options"][q["correct_index"]] == actual` and that no
  distractor equals it (whitespace-normalised), the usual assertion for output questions
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
BANK = HERE.parent / "seed_data" / "question_bank"
# React, react-dom, jsdom and @testing-library come from the frontend's own install, so React
# questions run against the exact versions the app uses (CommonJS `require`, no JSX).
NODE_MODULES = HERE.parents[2] / "frontend" / "node_modules"
TIMEOUT = 30


def _node_env() -> dict[str, str]:
    return {**os.environ, "NODE_PATH": str(NODE_MODULES)}


class CheckError(AssertionError):
    pass


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("`")).strip()


@dataclass
class Ctx:
    dsn: str | None

    def python(self, code: str) -> str:
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=TIMEOUT,
            check=False,
            cwd=HERE.parent.parent,
        )  # fmt: skip
        if result.returncode != 0:
            raise CheckError(f"python failed ({result.returncode}): {result.stderr.strip()[-800:]}")
        return result.stdout

    def python_status(self, code: str) -> tuple[int, str, str]:
        """Exit code, stdout and stderr, for snippets that are meant to fail."""
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=TIMEOUT,
            check=False,
            cwd=HERE.parent.parent,
        )  # fmt: skip
        return result.returncode, result.stdout, result.stderr

    def node(self, code: str, module: bool = False) -> str:
        cmd = ["node", "--input-type=module", "-e", code] if module else ["node", "-e", code]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT, check=False, env=_node_env()
        )
        if result.returncode != 0:
            raise CheckError(f"node failed ({result.returncode}): {result.stderr.strip()[-800:]}")
        return result.stdout

    def node_status(self, code: str, module: bool = False) -> tuple[int, str, str]:
        cmd = ["node", "--input-type=module", "-e", code] if module else ["node", "-e", code]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT, check=False, env=_node_env()
        )
        return result.returncode, result.stdout, result.stderr

    def sql(self, script: str) -> list[tuple[Any, ...]]:
        """Run `script` in a fresh schema and return the rows of its last statement."""
        if not self.dsn:
            raise CheckError("QCHECK_DSN is not set (run through `make question-checks`)")
        import psycopg

        schema = f"qcheck_{uuid.uuid4().hex[:12]}"
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            conn.execute(f'CREATE SCHEMA "{schema}"')
            try:
                with conn.cursor() as cur:
                    cur.execute(f'SET search_path TO "{schema}"')
                    rows: list[tuple[Any, ...]] = []
                    for statement in _statements(script):
                        cur.execute(statement)
                        rows = cur.fetchall() if cur.description else []
                    return rows
            finally:
                conn.execute(f'DROP SCHEMA "{schema}" CASCADE')

    def sql_error(self, script: str) -> str | None:
        """The SQLSTATE of the first failing statement, or None when every statement succeeds."""
        import psycopg

        try:
            self.sql(script)
        except psycopg.Error as exc:
            return exc.sqlstate
        return None

    def expect_only(self, q: dict[str, Any], actual: str) -> None:
        options = [_norm(o) for o in q["options"]]
        got = _norm(actual)
        marked = options[q["correct_index"]]
        if got != marked:
            raise CheckError(f"marked option {marked!r} but the code gives {got!r}")
        others = [o for i, o in enumerate(options) if i != q["correct_index"] and o == got]
        if others:
            raise CheckError(f"a distractor also equals the result: {others}")


def _statements(script: str) -> list[str]:
    """Split on semicolons at the end of a line (snippets don't use dollar-quoted bodies)."""
    parts = re.split(r";\s*(?:\n|$)", script)
    return [p.strip() for p in parts if p.strip() and not p.strip().startswith("--")]


def _questions() -> dict[str, tuple[str, dict[str, Any]]]:
    found: dict[str, tuple[str, dict[str, Any]]] = {}
    for path in sorted(BANK.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for q in doc.get("questions") or []:
            if q.get("check") == "execution":
                found[q["id"]] = (path.stem, q)
    return found


def _load(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"qcheck_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise CheckError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(only: set[str] | None, dsn: str | None) -> dict[str, str | None]:
    ctx = Ctx(dsn)
    results: dict[str, str | None] = {}
    for qid, (skill, q) in _questions().items():
        if only and qid not in only:
            continue
        path = HERE / skill / f"{qid.replace('-', '_')}.py"
        try:
            if not path.exists():
                raise CheckError(f"missing check file {path.relative_to(HERE)}")
            module = _load(path)
            module.check(ctx, q)
            results[qid] = None
        except Exception as exc:
            detail = str(exc) if isinstance(exc, CheckError) else traceback.format_exc(limit=3)
            results[qid] = detail.strip()
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute the bank's code questions")
    parser.add_argument("--only", nargs="*", help="question ids to run")
    parser.add_argument("--json", type=Path, help="write {id: null | failure} here")
    args = parser.parse_args(argv)
    results = run(set(args.only) if args.only else None, os.environ.get("QCHECK_DSN"))
    failed = {k: v for k, v in results.items() if v}
    for qid, detail in sorted(failed.items()):
        print(f"FAIL {qid}: {detail}")
    print(f"question checks: {len(results) - len(failed)} passed, {len(failed)} failed")
    if args.json:
        args.json.write_text(json.dumps(results, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
