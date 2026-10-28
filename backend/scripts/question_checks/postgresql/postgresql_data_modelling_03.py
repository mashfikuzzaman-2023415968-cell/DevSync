from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

SETUP = """
CREATE TABLE price (amount numeric(6,2));
INSERT INTO price VALUES (1234.567);
SELECT amount FROM price;
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    rows = ctx.sql(SETUP)
    ctx.expect_only(q, str(rows[0][0]))
