SETUP = """
CREATE TABLE scores (name text, score int);
INSERT INTO scores VALUES ('ann', 90), ('bob', 90), ('cy', 80), ('dee', 70);
SELECT rank() OVER (ORDER BY score DESC) AS r
FROM scores
ORDER BY score DESC, name;
"""


def check(ctx, q):
    ctx.expect_only(q, ", ".join(str(r[0]) for r in ctx.sql(SETUP)))
