from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

SETUP = """
CREATE TABLE tags (id serial PRIMARY KEY, name text UNIQUE);
INSERT INTO tags (name) VALUES ('sql');
INSERT INTO tags (name) VALUES ('sql') ON CONFLICT DO NOTHING;
INSERT INTO tags (name) VALUES ('db') RETURNING id;
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    rows = ctx.sql(SETUP)
    ctx.expect_only(q, str(rows[0][0]))
