BASE = """
CREATE TABLE subscriptions (id serial PRIMARY KEY, user_id int NOT NULL, status text NOT NULL);
"""
# What the requirement means: two cancelled rows are fine, a second active row is rejected.
ROWS_OK = """
INSERT INTO subscriptions (user_id, status) VALUES (1, 'cancelled');
INSERT INTO subscriptions (user_id, status) VALUES (1, 'cancelled');
INSERT INTO subscriptions (user_id, status) VALUES (1, 'active');
"""
SECOND_ACTIVE = "INSERT INTO subscriptions (user_id, status) VALUES (1, 'active');\n"


def _enforces(ctx, ddl):
    """True when the setup accepts the good rows and rejects a second active row."""
    return (
        ctx.sql_error(BASE + ddl + ROWS_OK) is None
        and ctx.sql_error(BASE + ddl + ROWS_OK + SECOND_ACTIVE) is not None
    )


def check(ctx, q):
    variants = {
        "partial unique index": "CREATE UNIQUE INDEX ON subscriptions (user_id) WHERE status = 'active';\n",
        "UNIQUE (user_id, status)": "ALTER TABLE subscriptions ADD UNIQUE (user_id, status);\n",
        "lookup": (
            "CREATE TABLE statuses (name text PRIMARY KEY);\n"
            "INSERT INTO statuses VALUES ('active'), ('cancelled'), ('expired');\n"
            "ALTER TABLE subscriptions ADD FOREIGN KEY (status) REFERENCES statuses (name);\n"
        ),
    }
    results = {name: _enforces(ctx, ddl) for name, ddl in variants.items()}
    assert results == {
        "partial unique index": True,
        "UNIQUE (user_id, status)": False,
        "lookup": False,
    }, results
    # CHECK with a subquery is not even allowed (0A000 feature_not_supported).
    sub = (
        "ALTER TABLE subscriptions ADD CHECK ((SELECT count(*) FROM subscriptions s "
        "WHERE s.user_id = user_id AND s.status = 'active') <= 1);\n"
    )
    assert ctx.sql_error(BASE + sub) == "0A000"
    options = q["options"]
    marked = options[q["correct_index"]]
    assert "partial unique index" in marked
    assert sum("UNIQUE (user_id, status)" in o for o in options) == 1
    assert sum("subquery" in o for o in options) == 1
    assert sum("lookup" in o for o in options) == 1
