from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

SETUP = """
CREATE TABLE scores (name text, score int);
INSERT INTO scores VALUES ('ann', 90), ('bob', 90), ('cy', 80), ('dee', 70);
SELECT rank() OVER (ORDER BY score DESC) AS r
FROM scores
ORDER BY score DESC, name;
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    ctx.expect_only(q, ", ".join(str(r[0]) for r in ctx.sql(SETUP)))
