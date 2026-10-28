from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx


def pytest_run(
    files: dict[str, str], *args: str, env: dict[str, str] | None = None
) -> tuple[int, str]:
    """Run pytest for real on `files` ({name: source}) in a temp dir; return (rc, output)."""
    with tempfile.TemporaryDirectory() as d:
        for name, src in files.items():
            Path(d, name).write_text(src)
        e = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **(env or {})}
        e.pop("PYTEST_ADDOPTS", None)
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "-p",
                "no:randomly",
                "-q",
                "--no-header",
                "-rA",
                *args,
            ],
            cwd=d,
            capture_output=True,
            text=True,
            timeout=120,
            env=e,
        )
        return r.returncode, r.stdout + r.stderr


def outcomes(out: str) -> dict[str, str]:
    return {
        m.group(2): m.group(1)
        for m in re.finditer(r"^(PASSED|FAILED|ERROR) \S+?::(\w+)", out, re.M)
    }


def split_files(snippet: str) -> dict[str, str]:
    files: dict[str, str] = {}
    name: str | None = None
    for line in snippet.splitlines():
        m = re.fullmatch(r"# (\w+\.py)", line)
        if m:
            name = m.group(1)
            files[name] = ""
        elif name:
            files[name] += line + "\n"
    return files


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    rc, out, err = ctx.python_status(q["code_snippet"])
    assert rc != 0 and "RuntimeError: unexpected" in err and out.strip() == "", (rc, out, err)
    # only with raise_server_exceptions=False does the script print 500
    alt = q["code_snippet"].replace(
        "TestClient(app)", "TestClient(app, raise_server_exceptions=False)"
    )
    assert ctx.python(alt).strip() == "500"
    assert q["options"][q["correct_index"]] == "It raises RuntimeError at the client.get call"
