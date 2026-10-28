from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import psycopg

if TYPE_CHECKING:
    from run_checks import Ctx


class Env:
    """One schema plus helper roles; cleans up after itself."""

    def __init__(self, ctx: Ctx, roles: list[str]) -> None:
        self.roles = roles
        self.schema = f"qcheck_{uuid.uuid4().hex[:12]}"
        assert ctx.dsn is not None
        self.conn = psycopg.connect(ctx.dsn, autocommit=True)

    def __enter__(self) -> psycopg.Connection[Any]:
        c = self.conn
        for r in self.roles:
            c.execute(f"DROP ROLE IF EXISTS {r}")
            c.execute(f"CREATE ROLE {r}")
        c.execute(f'CREATE SCHEMA "{self.schema}"')
        c.execute(f'SET search_path TO "{self.schema}"')
        for r in self.roles:
            c.execute(f'GRANT USAGE ON SCHEMA "{self.schema}" TO {r}')
        return c

    def __exit__(self, *exc: object) -> None:
        c = self.conn
        c.execute("RESET ROLE")
        c.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        for r in self.roles:
            c.execute(f"DROP ROLE IF EXISTS {r}")
        c.close()


def _scalar(conn: psycopg.Connection[Any], sql: str) -> Any:
    row = conn.execute(sql).fetchone()
    assert row is not None
    return row[0]


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    with Env(ctx, ["alice"]) as c:
        for stmt in (
            "CREATE TABLE notes (id int, owner text, body text)",
            "INSERT INTO notes VALUES (1, 'alice', 'x'), (2, 'alice', 'y'), (3, 'bob', 'z')",
            "ALTER TABLE notes ENABLE ROW LEVEL SECURITY",
            "CREATE POLICY own_notes ON notes USING (owner = current_user)",
            "GRANT SELECT ON notes TO alice",
            "SET ROLE alice",
        ):
            c.execute(stmt)
        count = _scalar(c, "SELECT count(*) FROM notes")
    ctx.expect_only(q, str(count))
