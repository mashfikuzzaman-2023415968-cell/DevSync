from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

BASE = """
CREATE TABLE tickets (
  id int GENERATED ALWAYS AS IDENTITY,
  title text
);
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    marked = q["options"][q["correct_index"]]
    assert marked.startswith("It fails because"), marked
    # The statement on line 5 fails with 428C9 (generated_always).
    assert ctx.sql_error(BASE + "INSERT INTO tickets (id, title) VALUES (10, 'a');\n") == "428C9"
    # So "stores 10", "ignores 10, stores 1" and "next id 11" are all false. Even the lenient
    # BY DEFAULT variant would not move the sequence to 11:
    rows = ctx.sql(
        BASE.replace("ALWAYS", "BY DEFAULT")
        + "INSERT INTO tickets (id, title) VALUES (10, 'a');\n"
        + "INSERT INTO tickets (title) VALUES ('b') RETURNING id;\n"
    )
    assert rows == [(1,)], rows
