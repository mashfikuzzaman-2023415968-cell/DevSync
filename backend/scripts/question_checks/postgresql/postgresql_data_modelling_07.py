SETUP = """
CREATE TABLE tags (id serial PRIMARY KEY, name text UNIQUE);
INSERT INTO tags (name) VALUES ('sql');
INSERT INTO tags (name) VALUES ('sql') ON CONFLICT DO NOTHING;
INSERT INTO tags (name) VALUES ('db') RETURNING id;
"""


def check(ctx, q):
    rows = ctx.sql(SETUP)
    ctx.expect_only(q, str(rows[0][0]))
