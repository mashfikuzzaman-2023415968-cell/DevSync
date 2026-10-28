SETUP = """
CREATE TABLE orders (id serial PRIMARY KEY, status text NOT NULL,
                     created_at timestamptz NOT NULL DEFAULT now(), total int NOT NULL);
INSERT INTO orders (status, total)
  SELECT CASE WHEN g % 200 = 0 THEN 'pending' ELSE 'shipped' END, g
  FROM generate_series(1, 200000) AS g;
"""
INDEXES = {
    "partial": "CREATE INDEX test_idx ON orders (status) WHERE status = 'pending'",
    "full": "CREATE INDEX test_idx ON orders (status)",
    "hash": "CREATE INDEX test_idx ON orders USING hash (status)",
    "composite": "CREATE INDEX test_idx ON orders (status, created_at, total)",
}


def _kind(option):
    if "partial" in option:
        return "partial"
    if "hash" in option:
        return "hash"
    if "composite" in option:
        return "composite"
    if "full B-tree" in option:
        return "full"
    raise AssertionError(option)


def check(ctx, q):
    sizes = {}
    for name, ddl in INDEXES.items():
        rows = ctx.sql(SETUP + ddl + ";\nANALYZE orders;\nSELECT pg_relation_size('test_idx');\n")
        sizes[name] = rows[0][0]
        plan = "\n".join(
            r[0]
            for r in ctx.sql(
                SETUP
                + ddl
                + ";\nANALYZE orders;\nEXPLAIN SELECT * FROM orders WHERE status = 'pending';\n"
            )
        )
        assert "test_idx" in plan, (name, plan)  # every candidate can serve the lookup
    smallest = min(sizes, key=sizes.get)
    assert smallest == "partial" and sorted(sizes.values())[0] < sorted(sizes.values())[1], sizes
    marked = _kind(q["options"][q["correct_index"]])
    assert marked == "partial"
    assert sorted(_kind(o) for o in q["options"]) == sorted(INDEXES)
