import uuid

import psycopg


class Env:
    """One schema plus helper roles; cleans up after itself."""

    def __init__(self, ctx, roles):
        self.roles = roles
        self.schema = f"qcheck_{uuid.uuid4().hex[:12]}"
        self.conn = psycopg.connect(ctx.dsn, autocommit=True)

    def __enter__(self):
        c = self.conn
        for r in self.roles:
            c.execute(f"DROP ROLE IF EXISTS {r}")
            c.execute(f"CREATE ROLE {r}")
        c.execute(f'CREATE SCHEMA "{self.schema}"')
        c.execute(f'SET search_path TO "{self.schema}"')
        for r in self.roles:
            c.execute(f'GRANT USAGE ON SCHEMA "{self.schema}" TO {r}')
        return c

    def __exit__(self, *exc):
        c = self.conn
        c.execute("RESET ROLE")
        c.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        for r in self.roles:
            c.execute(f"DROP ROLE IF EXISTS {r}")
        c.close()


def check(ctx, q):
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
        count = c.execute("SELECT count(*) FROM notes").fetchone()[0]
    ctx.expect_only(q, str(count))
