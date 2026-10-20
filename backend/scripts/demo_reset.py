"""Wipe user-scoped demo data so `make demo-reset` can reload the seed from a clean slate.

Runs as the migrator role (it owns the tables, so TRUNCATE is allowed and is not subject to RLS)
inside the migrate container, which has `MIGRATION_DATABASE_URL`. Catalog data that the migrations
seed — skills, the question bank and platform settings — has no foreign key to `users`, so it is
preserved; everything user-scoped cascades from `users`.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text


def main() -> int:
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        print("demo-reset: MIGRATION_DATABASE_URL is not set", file=sys.stderr)
        return 1
    engine = create_engine(url)
    with engine.begin() as conn:
        # The cascade reaches audit_log, whose append-only trigger blocks TRUNCATE; disable the
        # user triggers for this transaction (the migrator owns the table) and re-enable them.
        conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        conn.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
    engine.dispose()
    print("demo-reset: wiped user-scoped data (skills, questions and settings kept)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
