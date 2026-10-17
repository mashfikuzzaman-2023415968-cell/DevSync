"""Public homepage statistics function and settings v3 (Phase 2).

- `public_stats()`: SECURITY DEFINER aggregate for the homepage (spec §13.11 #3). Counting
  developers needs every user row, which RLS hides from web requests; the function returns one
  count and nothing else, so no user data can leak through it.
- Settings v3: rate limits for `public_stats` and `client_errors` (DECISIONS D22).

Revision ID: 0003_public_stats
Revises: 0002_identity_rls
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_public_stats"
down_revision: str | None = "0002_identity_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_V3 = Path(__file__).resolve().parent.parent / "seed" / "platform_settings_v3.json"
DML_ROLES = "devsync_app, devsync_worker"

PUBLIC_STATS = """
CREATE FUNCTION public_stats() RETURNS TABLE (developers bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT count(*) FROM users u WHERE u.role = 'DEVELOPER' AND u.status = 'ACTIVE'
$$;
"""


def upgrade() -> None:
    op.execute(PUBLIC_STATS)
    op.execute("REVOKE ALL ON FUNCTION public_stats() FROM PUBLIC, devsync_readonly")
    op.execute(f"GRANT EXECUTE ON FUNCTION public_stats() TO {DML_ROLES}")
    document = json.loads(SEED_V3.read_text(encoding="utf-8"))
    settings_table = sa.table(
        "platform_settings",
        sa.column("version", sa.Integer()),
        sa.column("values", postgresql.JSONB()),
        sa.column("reason", sa.Text()),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "version": 3,
                "values": document,
                "reason": "Rate limits for homepage stats and client error reports",
            }
        ],
    )


def downgrade() -> None:
    op.execute("ALTER TABLE platform_settings DISABLE TRIGGER platform_settings_immutable")
    op.execute("DELETE FROM platform_settings WHERE version = 3")
    op.execute("ALTER TABLE platform_settings ENABLE TRIGGER platform_settings_immutable")
    op.execute("DROP FUNCTION IF EXISTS public_stats()")
