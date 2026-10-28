def check(ctx, q):
    code, out, err = ctx.node_status(q["code_snippet"])
    assert code != 0, "process should crash"
    assert "caught" not in out, "catch must not run"
    assert "Error: boom" in err
    # marked option: crash, never prints; distractors claim a clean exit or a 'caught' line
    assert q["options"][q["correct_index"]].startswith("The process crashes")
