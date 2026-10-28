from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

L1 = "CREATE TABLE t (a int);\n"
L2 = "INSERT INTO t VALUES (1), (-1);\n"
L3 = "ALTER TABLE t ADD CONSTRAINT a_pos CHECK (a > 0) NOT VALID;\n"
L4 = "INSERT INTO t VALUES (-2);\n"


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    assert q["options"][q["correct_index"]] == "Line 4"
    assert ctx.sql_error(L1 + L2 + L3) is None  # lines 1-3 all succeed
    assert ctx.sql_error(L1 + L2 + L3 + L4) == "23514"  # line 4 fails
    # Without NOT VALID the failure would move to line 3 (the tempting wrong answer).
    assert ctx.sql_error(L1 + L2 + L3.replace(" NOT VALID", "")) == "23514"
