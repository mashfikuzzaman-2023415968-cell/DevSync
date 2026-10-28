SETUP = """
CREATE TABLE price (amount numeric(6,2));
INSERT INTO price VALUES (1234.567);
SELECT amount FROM price;
"""


def check(ctx, q):
    rows = ctx.sql(SETUP)
    ctx.expect_only(q, str(rows[0][0]))
