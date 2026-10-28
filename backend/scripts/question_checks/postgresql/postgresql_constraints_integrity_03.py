SETUP = """
CREATE TABLE items (price int CHECK (price > 0));
INSERT INTO items VALUES (NULL);
"""


def check(ctx, q):
    assert q["options"][q["correct_index"]] == "It succeeds and stores a NULL price"
    assert ctx.sql_error(SETUP) is None  # not a check (23514) or not-null (23502) failure
    assert ctx.sql(SETUP + "SELECT price FROM items;\n") == [(None,)]  # NULL, not 0
    # Contrast: a real violation does fail with 23514.
    assert ctx.sql_error(SETUP.replace("(NULL)", "(0)")) == "23514"
