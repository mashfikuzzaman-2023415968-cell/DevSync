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
    marked = q["options"][q["correct_index"]]
    assert marked == "It fails: new row violates row-level security policy for table notes"
    with Env(ctx, ["alice"]) as c:
        for stmt in (
            "CREATE TABLE notes (id int, owner text)",
            "ALTER TABLE notes ENABLE ROW LEVEL SECURITY",
            "CREATE POLICY own ON notes USING (owner = current_user)",
            "GRANT SELECT, INSERT ON notes TO alice",
            "SET ROLE alice",
        ):
            c.execute(stmt)
        error = None
        try:
            c.execute("INSERT INTO notes VALUES (1, 'bob')")
        except psycopg.Error as exc:
            error = exc
        c.execute("RESET ROLE")
        stored = c.execute("SELECT count(*) FROM notes").fetchone()[0]
    assert error is not None, "the insert must fail"
    message = str(error)
    assert "new row violates row-level security policy" in message, message
    assert "permission denied for table" not in message  # not a missing-privilege error
    assert stored == 0  # nothing was stored, so "succeeds but invisible" and "0 rows" are false
