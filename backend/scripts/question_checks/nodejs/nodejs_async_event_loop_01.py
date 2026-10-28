from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    code = q["code_snippet"]
    out = ctx.node(code)  # `node -e` runs the code as a CommonJS script
    ctx.expect_only(q, ", ".join(out.split()))
