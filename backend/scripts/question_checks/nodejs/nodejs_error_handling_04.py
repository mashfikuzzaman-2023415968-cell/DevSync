def check(ctx, q):
    out = ctx.node(q["code_snippet"])
    ctx.expect_only(q, ", ".join(out.split("\n")[:-1] if out.endswith("\n") else out.split("\n")))
