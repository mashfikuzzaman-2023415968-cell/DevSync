import threading
import time
import uuid

import psycopg


def check(ctx, q):
    marked = q["options"][q["correct_index"]]
    assert marked == "It detects the deadlock and aborts one transaction with an error"
    schema = f"qcheck_{uuid.uuid4().hex[:12]}"
    boss = psycopg.connect(ctx.dsn, autocommit=True)
    a = psycopg.connect(ctx.dsn, autocommit=True)
    b = psycopg.connect(ctx.dsn, autocommit=True)
    try:
        boss.execute(f'CREATE SCHEMA "{schema}"')
        for c in (boss, a, b):
            c.execute(f'SET search_path TO "{schema}"')
        boss.execute("CREATE TABLE accounts (id int PRIMARY KEY, balance int)")
        boss.execute("INSERT INTO accounts VALUES (1, 0), (2, 0)")
        a.execute("BEGIN")
        a.execute("UPDATE accounts SET balance = balance + 1 WHERE id = 1")
        b.execute("BEGIN")
        b.execute("UPDATE accounts SET balance = balance + 1 WHERE id = 2")
        outcome = {}

        def second(name, conn, row):
            try:
                conn.execute(f"UPDATE accounts SET balance = balance + 1 WHERE id = {row}")
                outcome[name] = "ok"
            except psycopg.Error as exc:
                outcome[name] = exc.sqlstate
                conn.execute("ROLLBACK")

        ta = threading.Thread(target=second, args=("A", a, 2))
        ta.start()
        time.sleep(0.5)  # A is now waiting for B's lock on row 2
        assert ta.is_alive()
        tb = threading.Thread(target=second, args=("B", b, 1))
        tb.start()
        ta.join(15)
        tb.join(15)
        assert not ta.is_alive() and not tb.is_alive(), "sessions hung: no deadlock detection"
        results = sorted(outcome.values())
        # Exactly one victim with 40P01, the other proceeds: not both aborted, not both waiting,
        # not both succeeding.
        assert results == ["40P01", "ok"], outcome
    finally:
        for c in (a, b):
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
        boss.execute(f'DROP SCHEMA "{schema}" CASCADE')
        boss.close()
