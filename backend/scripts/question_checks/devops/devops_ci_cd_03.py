import subprocess


def sh(script, shell="sh"):
    r = subprocess.run([shell, "-c", script], capture_output=True, text=True, timeout=10)
    return r.returncode, r.stdout.strip()


def check(ctx, q):
    script = q["code_snippet"]
    code, out = sh(script)
    ctx.expect_only(q, out)
    assert code == 0
    # distractors: set -e does stop at a bare failing command, and `|| true` is accepted syntax
    code2, out2 = sh("set -e\nfalse\necho deploying")
    assert code2 != 0 and out2 == ""
