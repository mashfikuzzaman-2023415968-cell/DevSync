import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def pytest_run(files, *args, env=None):
    """Run pytest for real on `files` ({name: source}) in a temp dir; return (rc, output)."""
    with tempfile.TemporaryDirectory() as d:
        for name, src in files.items():
            Path(d, name).write_text(src)
        e = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **(env or {})}
        e.pop("PYTEST_ADDOPTS", None)
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:randomly",
             "-q", "--no-header", "-rA", *args],
            cwd=d, capture_output=True, text=True, timeout=120, env=e,
        )
        return r.returncode, r.stdout + r.stderr


def outcomes(out):
    return {m.group(2): m.group(1) for m in re.finditer(r"^(PASSED|FAILED|ERROR) \S+?::(\w+)", out, re.M)}


def split_files(snippet):
    files, name = {}, None
    for line in snippet.splitlines():
        m = re.fullmatch(r"# (\w+\.py)", line)
        if m:
            name = m.group(1)
            files[name] = ""
        elif name:
            files[name] += line + "\n"
    return files

def check(ctx, q):
    ns = {}
    exec(q["code_snippet"], ns)  # noqa: S102 - our own snippet
    spec = lambda t: 0 if t >= 50 else 5
    wrong = [o for o in q["options"] if ns["shipping"](float(o)) != spec(float(o))]
    marked = q["options"][q["correct_index"]]
    assert wrong == [marked], f"inputs exposing the defect: {wrong}, marked {marked}"
