BASE = """
CREATE TABLE parent (id int PRIMARY KEY);
CREATE TABLE child (
  id int PRIMARY KEY,
  parent_id int REFERENCES parent (id) DEFERRABLE INITIALLY DEFERRED
);
"""
TX = """
BEGIN;
INSERT INTO child VALUES (1, 5);
INSERT INTO parent VALUES (5);
COMMIT;
"""


def check(ctx, q):
    assert q["options"][q["correct_index"]].startswith("None;")
    # No statement fails (lines 7, 8 and 9 all succeed).
    assert ctx.sql_error(BASE + TX) is None
    assert ctx.sql(BASE + TX + "SELECT count(*) FROM child;\n") == [(1,)]
    # The same script without DEFERRABLE fails on line 7 - what the first option imagines.
    plain = BASE.replace(" DEFERRABLE INITIALLY DEFERRED", "")
    assert ctx.sql_error(plain + "INSERT INTO child VALUES (1, 5);\n") == "23503"
    # A deferred violation is only reported by COMMIT when the parent never appears.
    assert ctx.sql_error(BASE + "BEGIN;\nINSERT INTO child VALUES (1, 5);\nCOMMIT;\n") == "23503"
