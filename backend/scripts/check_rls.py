"""Row-level security coverage check (spec §14.15).

Fails if any table in `public` is neither RLS-protected (ENABLE **and** FORCE)
nor listed in `app/db/rls_exempt.yml` with a reason. Enforced by the gate from
Phase 1 (when the RLS foundation lands); in Phase 0 the gate reports N/A.

Usage: `python scripts/check_rls.py` with MIGRATION_DATABASE_URL set (sync URL).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from sqlalchemy import create_engine, text

EXEMPT_FILE = Path(__file__).resolve().parents[1] / "app" / "db" / "rls_exempt.yml"
IGNORED = {"alembic_version"}


def load_exempt(path: Path = EXEMPT_FILE) -> dict[str, str]:
    """Return {table: reason}; every entry must have a non-empty reason."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tables = data.get("tables", {}) or {}
    bad = [t for t, reason in tables.items() if not str(reason or "").strip()]
    if bad:
        raise ValueError(f"rls_exempt.yml entries need a reason: {bad}")
    return {str(k): str(v) for k, v in tables.items()}


def find_unprotected(rows: list[tuple[str, bool, bool]], exempt: dict[str, str]) -> list[str]:
    """Tables without ENABLE+FORCE RLS that are not exempt (pure, unit-tested)."""
    return sorted(
        name
        for name, enabled, forced in rows
        if name not in IGNORED and name not in exempt and not (enabled and forced)
    )


def main() -> int:
    """CLI entry point."""
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        print("check_rls: MIGRATION_DATABASE_URL not set")
        return 2
    engine = create_engine(url)
    with engine.connect() as conn:
        rows = [
            (str(r[0]), bool(r[1]), bool(r[2]))
            for r in conn.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r'"
                )
            )
        ]
    missing = find_unprotected(rows, load_exempt())
    for name in missing:
        print(f"check_rls: table '{name}' has no ENABLE+FORCE row-level security and is not exempt")
    print(f"check_rls: {len(missing)} unprotected table(s)")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
