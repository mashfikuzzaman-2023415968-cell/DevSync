from __future__ import annotations

import threading
import time
import uuid
from typing import TYPE_CHECKING, Any

import psycopg

if TYPE_CHECKING:
    from run_checks import Ctx


def check(ctx: Ctx, q: dict[str, Any]) -> None:
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
        a.execute("BEGIN")
        a.execute("UPDATE accounts SET balance = balance - 30 WHERE id = 1")
        b.execute("BEGIN")
        outcome: dict[str, Any] = {}

        def b_update() -> None:
            try:
                b.execute("UPDATE accounts SET balance = balance - 20 WHERE id = 1")
                outcome["ok"] = True
            except psycopg.Error as exc:  # pragma: no cover - would disprove the answer
                outcome["error"] = exc

        t = threading.Thread(target=b_update)
        t.start()
        time.sleep(1.0)
        assert t.is_alive(), "B's UPDATE should be waiting for A's row lock"
        a.execute("COMMIT")
        t.join(10)
        assert not t.is_alive() and outcome.get("ok"), outcome
        b.execute("COMMIT")
        row = boss.execute("SELECT balance FROM accounts WHERE id = 1").fetchone()
        assert row is not None
        balance = row[0]
        ctx.expect_only(q, str(balance))
    finally:
        for c in (a, b):
            c.close()
        boss.execute(f'DROP SCHEMA "{schema}" CASCADE')
        boss.close()
