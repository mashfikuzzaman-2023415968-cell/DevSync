from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    # __filename is "[eval]" under `node -e`, so read a real file instead.
    code = q["code_snippet"].replace("__filename", "'/etc/passwd'")
    out = ctx.node(code)
    ctx.expect_only(q, ", ".join(out.split()))
