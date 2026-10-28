SETUP = """
CREATE TABLE users (email text UNIQUE);
INSERT INTO users VALUES (NULL), (NULL), ('a@x.com');
SELECT count(*) FROM users;
"""


def check(ctx, q):
    # Line 2 does not fail, and the table holds three rows.
    assert ctx.sql_error(SETUP) is None
    assert ctx.sql(SETUP) == [(3,)]
    assert q["options"][q["correct_index"]].endswith("returns 3")
    # Only the "returns 3" option is right: the others claim an error, 2 or 1.
    assert sum("returns 3" in o for o in q["options"]) == 1
