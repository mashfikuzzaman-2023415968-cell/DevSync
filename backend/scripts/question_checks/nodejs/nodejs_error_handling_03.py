from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    code, out, err = ctx.node_status(q["code_snippet"])
    assert code != 0, "process should crash"
    assert "handled" not in out
    assert "Error: fail" in err
    # fixing it with `await load()` makes catch run, proving the missing await is the cause
    fixed = q["code_snippet"].replace("    load();", "    await load();")
    code2, out2, _ = ctx.node_status(fixed)
    assert code2 == 0 and out2.strip() == "handled"
    assert q["options"][q["correct_index"]].startswith("The process crashes")
