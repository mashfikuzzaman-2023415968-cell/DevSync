from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

SETUP = """
CREATE TABLE payments (user_id int, amount int);
INSERT INTO payments VALUES (1, 100), (2, 50);
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    rows = ctx.sql(SETUP + "SELECT sum(amount) FROM payments WHERE user_id = 999;\n")
    options = q["options"]
    truth = {
        "One row containing NULL": len(rows) == 1 and rows[0][0] is None,
        "One row containing 0": len(rows) == 1 and rows[0][0] == 0,
        "No rows at all": len(rows) == 0,
        "An error about an empty group": ctx.sql_error(
            SETUP + "SELECT sum(amount) FROM payments WHERE user_id = 999;\n"
        )
        is not None,
    }
    assert set(truth) == set(options), options
    assert [o for o in options if truth[o]] == [options[q["correct_index"]]], truth
