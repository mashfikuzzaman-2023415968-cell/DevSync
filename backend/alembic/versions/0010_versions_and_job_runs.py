"""Profile versions (If-Match) and the scheduled jobs' run records (spec §10.1, §7.8, §11).

- `developer_profiles.version` / `client_profiles.version`: optimistic concurrency for the profile
  PATCHes (§10.1 "mutable resources return version; updates send If-Match"). A profile that was
  never saved has no row and reports version 0.
- `jobs`: each scheduled job now records a row per run (start, finish, status, error code;
  §11 "each job records progress in `jobs`"). The table and its RLS (requester/admin read,
  SYSTEM writes, FORCE RLS) exist since 0001/0002; this adds the one missing policy, a SYSTEM-only
  DELETE so `lifecycle.expire` can prune old system run records (nobody else may delete), and an
  index for that prune and for the admin's newest-first listing.

Revision ID: 0010_versions_and_job_runs
Revises: 0009_bid_rules
Create Date: 2026-10-24 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_versions_and_job_runs"
down_revision: str | None = "0009_bid_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROFILE_TABLES = ("developer_profiles", "client_profiles")


def upgrade() -> None:
    for table in PROFILE_TABLES:
        op.add_column(table, sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        op.create_check_constraint(op.f(f"ck_{table}_version_positive"), table, "version >= 1")
    op.execute("CREATE POLICY jobs_delete ON jobs FOR DELETE TO devsync_worker USING (is_system())")
    op.create_index(op.f("ix_jobs_type_created_at"), "jobs", ["type", "created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_jobs_type_created_at"), table_name="jobs")
    op.execute("DROP POLICY IF EXISTS jobs_delete ON jobs")
    for table in reversed(PROFILE_TABLES):
        op.drop_constraint(op.f(f"ck_{table}_version_positive"), table, type_="check")
        op.drop_column(table, "version")
