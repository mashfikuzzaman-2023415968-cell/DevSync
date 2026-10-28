from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import psycopg

if TYPE_CHECKING:
    from run_checks import Ctx

ROLE = "reporting"


def _attempt(ctx: Ctx, statement: str) -> tuple[str | None, bool]:
    """Run `statement` against a fresh orders table that `reporting` can SELECT from.

    Returns (sqlstate or None, whether reporting still holds SELECT afterwards)."""
    schema = f"qcheck_{uuid.uuid4().hex[:12]}"
    assert ctx.dsn is not None
    conn = psycopg.connect(ctx.dsn, autocommit=True)
    try:
        conn.execute(f"DROP ROLE IF EXISTS {ROLE}")
        conn.execute(f"CREATE ROLE {ROLE}")
        conn.execute(f'CREATE SCHEMA "{schema}"')
        conn.execute(f'SET search_path TO "{schema}"')
        conn.execute("CREATE TABLE orders (id int)")
        conn.execute(f"GRANT SELECT ON orders TO {ROLE}")
        state: str | None = None
        try:
            conn.execute(statement)
        except psycopg.Error as exc:
            state = exc.sqlstate
        row = conn.execute(f"SELECT has_table_privilege('{ROLE}', 'orders', 'SELECT')").fetchone()
        assert row is not None
        has: bool = row[0]
        return state, has
    finally:
        conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
        conn.execute(f"DROP ROLE IF EXISTS {ROLE}")
        conn.close()


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    for i, option in enumerate(q["options"]):
        state, still_has = _attempt(ctx, option)
        worked = state is None and not still_has  # statement ran and the privilege is gone
        assert worked == (i == q["correct_index"]), (option, state, still_has)
        if i != q["correct_index"]:
            assert state is not None, option  # the wrong statements are not valid PostgreSQL
