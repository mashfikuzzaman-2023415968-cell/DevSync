from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import psycopg

if TYPE_CHECKING:
    from run_checks import Ctx


def _run(ctx: Ctx, isolation: str) -> tuple[psycopg.Error | None, int]:
    schema = f"qcheck_{uuid.uuid4().hex[:12]}"
    assert ctx.dsn is not None
    boss = psycopg.connect(ctx.dsn, autocommit=True)
    a = psycopg.connect(ctx.dsn, autocommit=True)
    b = psycopg.connect(ctx.dsn, autocommit=True)
    try:
        boss.execute(f'CREATE SCHEMA "{schema}"')
        for c in (boss, a, b):
            c.execute(f'SET search_path TO "{schema}"')
        boss.execute("CREATE TABLE accounts (id int PRIMARY KEY, balance int)")
        boss.execute("INSERT INTO accounts VALUES (1, 100)")
        a.execute(f"BEGIN ISOLATION LEVEL {isolation}")
        a.execute("SELECT balance FROM accounts WHERE id = 1").fetchall()
        b.execute("UPDATE accounts SET balance = 50 WHERE id = 1")  # autocommits
        error: psycopg.Error | None = None
        try:
            a.execute("UPDATE accounts SET balance = balance - 10 WHERE id = 1")
        except psycopg.Error as exc:
            error = exc
        if error is None:
            a.execute("COMMIT")
        else:
            a.execute("ROLLBACK")
        row = boss.execute("SELECT balance FROM accounts WHERE id = 1").fetchone()
        assert row is not None
        balance: int = row[0]
        return error, balance
    finally:
        for c in (a, b):
            c.close()
        boss.execute(f'DROP SCHEMA "{schema}" CASCADE')
        boss.close()


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    marked = q["options"][q["correct_index"]]
    assert marked.startswith("It fails with a serialization failure"), marked
    error, balance = _run(ctx, "REPEATABLE READ")
    assert error is not None and error.sqlstate == "40001", error
    assert "could not serialize access due to concurrent update" in str(error)
    # A's update never applied: the balance is B's 50, so neither 40 nor 90 was ever stored.
    assert balance == 50, balance
    # Contrast (the "40" option is what READ COMMITTED would do, not REPEATABLE READ):
    error_rc, balance_rc = _run(ctx, "READ COMMITTED")
    assert error_rc is None and balance_rc == 40, (error_rc, balance_rc)
