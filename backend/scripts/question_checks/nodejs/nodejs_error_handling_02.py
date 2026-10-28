from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    code, out, err = ctx.node_status(q["code_snippet"])
    assert code != 0, "process should crash"
    assert "caught" not in out, "catch must not run"
    assert "Error: boom" in err
    # marked option: crash, never prints; distractors claim a clean exit or a 'caught' line
    assert q["options"][q["correct_index"]].startswith("The process crashes")
