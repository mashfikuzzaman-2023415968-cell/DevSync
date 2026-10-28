import subprocess


def bash(script):
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10)
    return r.returncode, r.stdout.strip()


def check(ctx, q):
    code, out = bash(q["code_snippet"])
    assert (code, out) == (0, "deploying"), (code, out)  # marked option: prints deploying
    # distractor 2: with pipefail the script would stop, so plain set -e does not cover pipelines
    code2, out2 = bash("set -eo pipefail\nfalse | cat\necho deploying")
    assert code2 != 0 and out2 == ""
    # distractor 3: set -e applies to later lines too
    code3, out3 = bash("set -e\necho a\nfalse\necho b")
    assert code3 != 0 and out3 == "a"
    # distractor 4: cat succeeds on empty input
    code4, _ = bash("true | cat")
    assert code4 == 0
