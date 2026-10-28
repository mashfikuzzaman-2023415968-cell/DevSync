from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    out = ctx.node(q["code_snippet"])
    ctx.expect_only(q, out)
