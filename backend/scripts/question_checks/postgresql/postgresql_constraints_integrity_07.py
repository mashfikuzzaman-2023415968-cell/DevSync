from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

BASE = """
CREATE TABLE customers (id int PRIMARY KEY);
CREATE TABLE orders (id int PRIMARY KEY, customer_id int REFERENCES customers (id));
INSERT INTO customers VALUES (1);
INSERT INTO orders VALUES (10, 1);
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    assert q["options"][q["correct_index"]] == "The DELETE fails with a foreign key violation"
    assert ctx.sql_error(BASE + "DELETE FROM customers WHERE id = 1;\n") == "23503"
    # The alternatives only happen with an explicit ON DELETE clause, not by default.
    for clause in ("CASCADE", "SET NULL"):
        ddl = BASE.replace(
            "REFERENCES customers (id)", f"REFERENCES customers (id) ON DELETE {clause}"
        )
        assert ctx.sql_error(ddl + "DELETE FROM customers WHERE id = 1;\n") is None
