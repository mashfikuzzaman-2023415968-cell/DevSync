def check(ctx, q):
    # __filename is "[eval]" under `node -e`, so read a real file instead.
    code = q["code_snippet"].replace("__filename", "'/etc/passwd'")
    out = ctx.node(code)
    ctx.expect_only(q, ", ".join(out.split()))
