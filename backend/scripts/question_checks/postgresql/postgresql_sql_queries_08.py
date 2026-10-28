from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

SETUP = """
CREATE TABLE orders (customer_id int, total int, created_on date);
INSERT INTO orders VALUES
  (1, 10, '2024-01-01'), (1, 20, '2024-01-03'),
  (2, 7, '2024-01-01'), (2, 5, '2024-01-02');
SELECT DISTINCT ON (customer_id) customer_id, total
FROM orders
ORDER BY customer_id, created_on DESC;
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    ctx.expect_only(q, ", ".join(f"({a}, {b})" for a, b in ctx.sql(SETUP)))
