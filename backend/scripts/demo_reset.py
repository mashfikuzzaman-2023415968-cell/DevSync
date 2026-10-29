"""Wipe user-scoped demo data so `make demo-reset` can reload the seed from a clean slate.

Runs as the migrator role (it owns the tables, so TRUNCATE is allowed and is not subject to RLS)
inside the migrate container, which has `MIGRATION_DATABASE_URL`. Catalog data that the migrations
seed — skills, competencies and platform settings — has no foreign key to `users`, so it is
preserved; everything user-scoped cascades from `users`. The question bank is catalog data too,
but it names its human reviewer (`reviewed_by_user`), so a cascade would empty it: its rows are
kept across the truncate, without the reviewer link (the accounts are gone).
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import Connection, MetaData, Table, create_engine, select, text

# Catalog tables with a foreign key to `users`: their rows survive the reset (statements below).
# tests/integration/test_demo_reset.py fails when another one appears, so it can't be emptied
# unnoticed.
PRESERVED = ("question_bank",)


def reset(conn: Connection) -> None:
    """Truncate every user and what cascades from them, keeping the preserved catalog rows."""
    # Held in memory (a few hundred rows): the migrator may not create temporary tables.
    bank = Table("question_bank", MetaData(), autoload_with=conn)
    rows = [{**row, "reviewed_by_user": None} for row in conn.execute(select(bank)).mappings()]
    # The cascade reaches audit_log, whose append-only trigger blocks TRUNCATE; disable the user
    # triggers for this transaction (the migrator owns the table) and re-enable them.
    conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
    conn.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))
    conn.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
    if rows:
        conn.execute(bank.insert(), rows)


def main() -> int:
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        print("demo-reset: MIGRATION_DATABASE_URL is not set", file=sys.stderr)
        return 1
    engine = create_engine(url)
    with engine.begin() as conn:
        reset(conn)
    engine.dispose()
    print("demo-reset: wiped user-scoped data (skills, questions and settings kept)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
