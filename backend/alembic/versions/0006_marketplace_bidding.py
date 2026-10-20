"""Sealed bids, availability reservations, reputation snapshots and project search (Phase 5).

- Tables from spec §7.4 (`bids`, `availability_reservations`) and §7.7 (`reputation_snapshots`).
- Full-text search on projects: a generated `search_vector` (title + summary) with a GIN index;
  skills are a structured filter joined at query time (spec §7.3, §9.2).
- Row-level security on every new table (§14.15, §14.13 row 5): **sealed bids** — a bid and a
  reservation are visible only to the bidding developer, the project's client and admins, never to
  other developers; writes are limited to the bidder while the project is `BIDDING` (plus SYSTEM
  for the seed and later jobs). Reputation snapshots are a public read for any authenticated user
  and SYSTEM-only to write. A `project_is_bidding()` SECURITY DEFINER helper lets the bid policies
  check the project status without the caller's RLS.

Revision ID: 0006_marketplace_bidding
Revises: 0005_projects_planning
Create Date: 2026-10-20 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_marketplace_bidding"
down_revision: str | None = "0005_projects_planning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DML_ROLES = "devsync_app, devsync_worker"

# SECURITY DEFINER (owned by the migrator) so a bid policy can read `projects.status` without the
# caller's RLS and without recursing into the projects policies.
HELPERS = r"""
CREATE FUNCTION project_is_bidding(p_project uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT EXISTS (SELECT 1 FROM projects WHERE id = p_project AND status = 'BIDDING')
$$;
"""
HELPER_FUNCTIONS = ("project_is_bidding(uuid)",)

# DDL built only from fixed role names (no user input); roles inlined so the SQL-injection linter
# sees no string-formatted SQL.
POLICIES = """
-- bids: sealed. Readable by the bidder, the project's client and admins — never other developers.
ALTER TABLE bids ENABLE ROW LEVEL SECURITY;
ALTER TABLE bids FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON bids TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY bid_select ON bids FOR SELECT TO devsync_app, devsync_worker
  USING (developer_id = app_uid() OR is_project_client(project_id) OR is_admin());
CREATE POLICY bid_insert ON bids FOR INSERT TO devsync_app, devsync_worker
  WITH CHECK (
    (developer_id = app_uid() AND app_role() = 'DEVELOPER' AND project_is_bidding(project_id))
    OR app_role() = 'SYSTEM'
  );
CREATE POLICY bid_update ON bids FOR UPDATE TO devsync_app, devsync_worker
  USING ((developer_id = app_uid() AND project_is_bidding(project_id)) OR app_role() = 'SYSTEM')
  WITH CHECK ((developer_id = app_uid() AND project_is_bidding(project_id)) OR app_role() = 'SYSTEM');

-- availability_reservations: the developer, the project's client and admins read; the developer
-- or SYSTEM write (invitations create them in Phase 8).
ALTER TABLE availability_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE availability_reservations FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON availability_reservations TO devsync_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY reservation_select ON availability_reservations FOR SELECT TO devsync_app, devsync_worker
  USING (developer_id = app_uid() OR is_project_client(project_id) OR is_admin());
CREATE POLICY reservation_write ON availability_reservations FOR ALL TO devsync_app, devsync_worker
  USING (developer_id = app_uid() OR app_role() = 'SYSTEM')
  WITH CHECK (developer_id = app_uid() OR app_role() = 'SYSTEM');

-- reputation_snapshots: a public value for any authenticated user; SYSTEM-only to write.
ALTER TABLE reputation_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE reputation_snapshots FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON reputation_snapshots TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY snapshot_select ON reputation_snapshots FOR SELECT TO devsync_app, devsync_worker
  USING (app_uid() IS NOT NULL OR is_admin());
CREATE POLICY snapshot_write ON reputation_snapshots FOR ALL TO devsync_app, devsync_worker
  USING (app_role() = 'SYSTEM') WITH CHECK (app_role() = 'SYSTEM');
"""


def upgrade() -> None:
    op.create_table(
        "bids",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("developer_id", sa.UUID(), nullable=False),
        sa.Column("slot_id", sa.UUID(), nullable=False),
        sa.Column("price_paisa", sa.BigInteger(), nullable=False),
        sa.Column("days_needed", sa.SmallInteger(), nullable=False),
        sa.Column("proposal", sa.Text(), server_default="", nullable=False),
        sa.Column("expected_contribution", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "portfolio_item_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("hours_per_week_committed", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "WITHDRAWN",
                "INELIGIBLE",
                "SELECTED",
                "NOT_SELECTED",
                "ACCEPTED",
                "DECLINED",
                "EXPIRED",
                name="bid_status",
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "ineligible_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("price_paisa > 0", name=op.f("ck_bids_price_positive")),
        sa.CheckConstraint("days_needed BETWEEN 1 AND 365", name=op.f("ck_bids_days_range")),
        sa.CheckConstraint(
            "hours_per_week_committed BETWEEN 1 AND 168",
            name=op.f("ck_bids_hours_committed_range"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_bids_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["users.id"],
            name=op.f("fk_bids_developer_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["slot_id"],
            ["project_slots.id"],
            name=op.f("fk_bids_slot_id_project_slots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bids")),
    )
    op.create_index(
        "one_active_bid_per_developer",
        "bids",
        ["project_id", "developer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index("ix_bids_project_status", "bids", ["project_id", "status"], unique=False)
    op.create_index("ix_bids_developer_status", "bids", ["developer_id", "status"], unique=False)

    op.create_table(
        "availability_reservations",
        sa.Column("developer_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("hours_per_week", sa.SmallInteger(), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("TENTATIVE", "CONFIRMED", "RELEASED", name="reservation_status"),
            server_default="TENTATIVE",
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "to_date >= from_date", name=op.f("ck_availability_reservations_reservation_dates")
        ),
        sa.CheckConstraint(
            "hours_per_week BETWEEN 1 AND 168",
            name=op.f("ck_availability_reservations_reservation_hours_range"),
        ),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["users.id"],
            name=op.f("fk_availability_reservations_developer_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_availability_reservations_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_availability_reservations")),
    )
    op.create_index(
        "ix_reservations_developer_status",
        "availability_reservations",
        ["developer_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_reservations_project", "availability_reservations", ["project_id"], unique=False
    )

    op.create_table(
        "reputation_snapshots",
        sa.Column("developer_id", sa.UUID(), nullable=False),
        sa.Column("omega", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("x", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("xm", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("beta", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("mu", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("t", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("c", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("p", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("completed_projects", sa.Integer(), server_default="0", nullable=False),
        sa.Column("distinct_clients", sa.Integer(), server_default="0", nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *[
            sa.CheckConstraint(
                f"{col} BETWEEN 0 AND 1", name=op.f(f"ck_reputation_snapshots_{col}_range")
            )
            for col in ("omega", "x", "xm", "beta", "mu", "t", "c", "p")
        ],
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["users.id"],
            name=op.f("fk_reputation_snapshots_developer_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reputation_snapshots")),
        sa.UniqueConstraint("developer_id", name=op.f("uq_reputation_snapshots_developer_id")),
    )

    # Project full-text search (title + summary); skills are filtered via a join at query time.
    op.add_column(
        "projects",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(summary, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_projects_search", "projects", ["search_vector"], unique=False, postgresql_using="gin"
    )

    # Helper and RLS policies.
    op.execute(HELPERS)
    for fn in HELPER_FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, devsync_readonly")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {DML_ROLES}")
    op.execute(POLICIES)


def downgrade() -> None:
    # Drop the tables first (their RLS policies and indexes go with them), then the search column
    # and the helper function, then the enum types.
    op.drop_index("ix_projects_search", table_name="projects")
    op.drop_column("projects", "search_vector")
    op.drop_table("reputation_snapshots")
    op.drop_index("ix_reservations_project", table_name="availability_reservations")
    op.drop_index("ix_reservations_developer_status", table_name="availability_reservations")
    op.drop_table("availability_reservations")
    op.drop_index("ix_bids_developer_status", table_name="bids")
    op.drop_index("ix_bids_project_status", table_name="bids")
    op.drop_index("one_active_bid_per_developer", table_name="bids")
    op.drop_table("bids")
    op.execute("DROP FUNCTION IF EXISTS project_is_bidding(uuid)")
    op.execute("DROP TYPE IF EXISTS bid_status")
    op.execute("DROP TYPE IF EXISTS reservation_status")
