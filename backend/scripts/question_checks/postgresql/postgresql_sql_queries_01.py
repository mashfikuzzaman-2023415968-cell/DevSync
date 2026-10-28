from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

SETUP = """
CREATE TABLE results (score int);
INSERT INTO results VALUES (10), (NULL), (30);
SELECT count(*), count(score) FROM results;
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    row = ctx.sql(SETUP)[0]
    ctx.expect_only(q, f"{row[0]}, {row[1]}")
