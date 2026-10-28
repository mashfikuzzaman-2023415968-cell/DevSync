SETUP = """
CREATE TABLE users (id serial PRIMARY KEY, email text NOT NULL);
INSERT INTO users (email)
  SELECT 'User' || g || '@Example.com' FROM generate_series(1, 50000) AS g;
CREATE INDEX users_email_idx ON users (email);
"""
QUERY = "SELECT * FROM users WHERE lower(email) = 'user77@example.com'"


def _plan(ctx, change):
    rows = ctx.sql(
        SETUP + change + ";\nANALYZE users;\nSET enable_seqscan = off;\nEXPLAIN " + QUERY + ";\n"
    )
    return "\n".join(r[0] for r in rows)


def _uses_index(plan):
    return "Index Scan" in plan or "Bitmap Index Scan" in plan or "Index Only Scan" in plan


def check(ctx, q):
    # Baseline: even with seq scans discouraged, no index can serve the lower(email) condition.
    assert not _uses_index(_plan(ctx, "SELECT 1")), "baseline already uses an index"
    changes = {
        "CREATE INDEX ON users (lower(email))": "CREATE INDEX ON users (lower(email))",
        "CREATE INDEX ON users (email DESC)": "CREATE INDEX ON users (email DESC)",
        "Run ANALYZE users": "ANALYZE users",
        "Recreate users_email_idx with USING hash": (
            "DROP INDEX users_email_idx;\nCREATE INDEX users_email_idx ON users USING hash (email)"
        ),
    }
    assert set(changes) == set(q["options"]), q["options"]
    for i, option in enumerate(q["options"]):
        got = _uses_index(_plan(ctx, changes[option]))
        assert got == (i == q["correct_index"]), (option, got)
