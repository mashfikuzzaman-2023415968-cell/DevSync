SETUP = """
CREATE TABLE a (id int);
CREATE TABLE b (id int);
INSERT INTO a VALUES (1), (2), (3);
INSERT INTO b VALUES (2), (NULL);
SELECT count(*) FROM a WHERE id NOT IN (SELECT id FROM b);
"""


def check(ctx, q):
    ctx.expect_only(q, str(ctx.sql(SETUP)[0][0]))
