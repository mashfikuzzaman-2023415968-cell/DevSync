from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

SETUP = """
CREATE TABLE a (id int);
CREATE TABLE b (id int);
INSERT INTO a VALUES (1), (2), (3);
INSERT INTO b VALUES (2), (3), (4);
SELECT count(*)
FROM a LEFT JOIN b ON a.id = b.id
WHERE b.id > 2;
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    ctx.expect_only(q, str(ctx.sql(SETUP)[0][0]))
