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
    with Env(ctx, ["bob"]) as c:
        c.execute(f'GRANT CREATE ON SCHEMA "{_scalar(c, "SELECT current_schema()")}" TO bob')
        c.execute("SET ROLE bob")  # bob is not a superuser and has no BYPASSRLS
        for stmt in (
            "CREATE TABLE notes (id int, owner text)",
            "INSERT INTO notes VALUES (1, 'alice'), (2, 'alice'), (3, 'bob')",
            "ALTER TABLE notes ENABLE ROW LEVEL SECURITY",
            "CREATE POLICY own_notes ON notes USING (owner = current_user)",
        ):
            c.execute(stmt)
        owner_count = _scalar(c, "SELECT count(*) FROM notes")
        ctx_ok = _scalar(
            c, "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        assert ctx_ok is False
        # With FORCE the policy applies to the owner too: bob would see only his own row.
        c.execute("ALTER TABLE notes FORCE ROW LEVEL SECURITY")
        forced = _scalar(c, "SELECT count(*) FROM notes")
    assert forced == 1, forced
    ctx.expect_only(q, str(owner_count))
