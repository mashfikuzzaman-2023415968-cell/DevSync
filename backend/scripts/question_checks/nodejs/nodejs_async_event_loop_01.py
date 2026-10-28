def check(ctx, q):
    code = q["code_snippet"]
    out = ctx.node(code)  # `node -e` runs the code as a CommonJS script
    ctx.expect_only(q, ", ".join(out.split()))
