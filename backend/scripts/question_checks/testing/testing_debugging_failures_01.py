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
    src = q["code_snippet"]
    for name in ("test_a", "test_b"):
        rc, out = pytest_run({"test_t.py": src}, "-k", name)
        assert rc == 0, out
    rc, out = pytest_run({"test_t.py": src}, "-vv")
    assert outcomes(out) == {"test_a": "PASSED", "test_b": "FAILED"}, out
    assert out.index("test_a") < out.index("test_b")  # default order is file order, not random
    assert "['x', 'y'] == ['y']" in out.replace('"', "'"), out
    fixed = src.replace("tags=[]", "tags=None").replace("    tags.append(tag)", "    tags = [] if tags is None else tags\n    tags.append(tag)")
    rc2, out2 = pytest_run({"test_t.py": fixed})
    assert rc2 == 0, out2
    assert q["options"][q["correct_index"]].startswith("One default list is shared")
