SETUP = """
CREATE TABLE customers (id int PRIMARY KEY);
CREATE TABLE orders (id int PRIMARY KEY, customer_id int);
INSERT INTO customers VALUES (1), (2), (3);
INSERT INTO orders VALUES (10, 1), (11, 1), (12, 2);
"""
# Customers 1 and 2 have orders; customer 3 never ordered.
QUERIES = {
    "INNER JOIN": "SELECT c.id FROM customers c JOIN orders o ON o.customer_id = c.id WHERE o.id IS NULL",
    "= NULL": "SELECT c.id FROM customers c LEFT JOIN orders o ON o.customer_id = c.id WHERE o.id = NULL",
    "HAVING": "SELECT c.id FROM customers c LEFT JOIN orders o ON o.customer_id = c.id GROUP BY c.id HAVING count(*) = 0",
    "IS NULL": "SELECT c.id FROM customers c LEFT JOIN orders o ON o.customer_id = c.id WHERE o.id IS NULL",
}


def _query_for(option):
    for key in ("INNER JOIN", "= NULL", "HAVING", "IS NULL"):  # most specific first
        if key in option:
            return QUERIES[key]
    raise AssertionError(option)


def check(ctx, q):
    for i, option in enumerate(q["options"]):
        got = sorted(r[0] for r in ctx.sql(SETUP + _query_for(option) + ";\n"))
        is_right = got == [3]
        assert is_right == (i == q["correct_index"]), (option, got)
