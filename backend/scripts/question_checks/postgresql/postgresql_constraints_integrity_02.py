SETUP = """
CREATE TABLE parent (id int PRIMARY KEY);
CREATE TABLE child (
  id int PRIMARY KEY,
  parent_id int REFERENCES parent (id) ON DELETE CASCADE
);
INSERT INTO parent VALUES (1), (2);
INSERT INTO child VALUES (10, 1), (11, 1), (12, 2);
DELETE FROM parent WHERE id = 1;
SELECT count(*) FROM child;
"""


def check(ctx, q):
    ctx.expect_only(q, str(ctx.sql(SETUP)[0][0]))
