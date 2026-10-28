SETUP = """
CREATE TABLE results (score int);
INSERT INTO results VALUES (10), (NULL), (30);
SELECT count(*), count(score) FROM results;
"""


def check(ctx, q):
    row = ctx.sql(SETUP)[0]
    ctx.expect_only(q, f"{row[0]}, {row[1]}")
