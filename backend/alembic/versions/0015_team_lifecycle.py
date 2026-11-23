"""Team lifecycle (Phase 8): lead changes, team repair, removal requests (spec §7.4, D118–D139).

- `lead_change_requests` (§1.6 rule 4, D132): readable by the team's client and its ACTIVE
  members (the service narrows a member to their own) and admins.
- `repair_proposals` (§9.9, D128): readable by the team's client and admins only — developers never
  see candidate lists (sealed bids). Inputs (team, departed member, seed, params, snapshot,
  settings version) are immutable once written and proposals are never deleted (trigger + grants),
  like `formation_runs`.
- `member_removal_requests` (D121): readable by the team's client and admins.
- `team_members.lead_declined_at` (D131); `project_slots.reopened_until`, `reopen_count` (D126).
- `is_team_member()` now counts only INVITED, ACTIVE and COMPLETED members (D130): someone who
  declined, expired, left or was removed sees only their own row and invitation. The downgrade
  restores 0014's definition.
- Every write is SYSTEM-only (`is_system()`, D99); new definer helpers pin `search_path`.

Revision ID: 0015_team_lifecycle
Revises: 0014_team_formation
Create Date: 2026-11-23 17:07:44.292726+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_team_lifecycle"
down_revision: str | None = "0014_team_formation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DML_ROLES = "devsync_app, devsync_worker"

HELPERS = r"""
CREATE OR REPLACE FUNCTION is_team_member(p_team uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL
     AND EXISTS (SELECT 1 FROM team_members WHERE team_id = p_team AND developer_id = app_uid()
                 AND status IN ('INVITED', 'ACTIVE', 'COMPLETED'))
$$;

CREATE FUNCTION is_active_team_member(p_team uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL
     AND EXISTS (SELECT 1 FROM team_members WHERE team_id = p_team AND developer_id = app_uid()
                 AND status = 'ACTIVE')
$$;

CREATE FUNCTION is_member_client(p_member uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT EXISTS (SELECT 1 FROM team_members m JOIN teams t ON t.id = m.team_id
                 WHERE m.id = p_member AND is_project_client(t.project_id))
$$;

-- A proposal's inputs are frozen once written; only its result side changes; never deleted.
CREATE FUNCTION repair_proposal_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'repair proposals are kept' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.team_id IS DISTINCT FROM OLD.team_id
     OR NEW.departed_member_id IS DISTINCT FROM OLD.departed_member_id
     OR NEW.settings_version IS DISTINCT FROM OLD.settings_version
     OR NEW.seed IS DISTINCT FROM OLD.seed
     OR NEW.params IS DISTINCT FROM OLD.params
     OR NEW.candidate_snapshot IS DISTINCT FROM OLD.candidate_snapshot THEN
    RAISE EXCEPTION 'a repair proposal''s inputs are immutable'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END;
$$;
"""
NEW_HELPERS = ("is_active_team_member(uuid)", "is_member_client(uuid)")

RESTORE_TEAM_MEMBER = r"""
CREATE OR REPLACE FUNCTION is_team_member(p_team uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL
     AND EXISTS (SELECT 1 FROM team_members WHERE team_id = p_team AND developer_id = app_uid())
$$;
"""

POLICIES = """
ALTER TABLE lead_change_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_change_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON lead_change_requests TO devsync_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY lead_change_select ON lead_change_requests FOR SELECT TO devsync_app, devsync_worker
  USING (is_team_client(team_id) OR is_active_team_member(team_id) OR is_admin() OR is_system());
CREATE POLICY lead_change_write ON lead_change_requests FOR ALL TO devsync_app, devsync_worker
  USING (is_system()) WITH CHECK (is_system());

ALTER TABLE repair_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE repair_proposals FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON repair_proposals TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY repair_select ON repair_proposals FOR SELECT TO devsync_app, devsync_worker
  USING (is_team_client(team_id) OR is_admin() OR is_system());
CREATE POLICY repair_write ON repair_proposals FOR ALL TO devsync_app, devsync_worker
  USING (is_system()) WITH CHECK (is_system());
CREATE TRIGGER repair_proposal_guard BEFORE UPDATE OR DELETE ON repair_proposals
  FOR EACH ROW EXECUTE FUNCTION repair_proposal_guard();

ALTER TABLE member_removal_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE member_removal_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON member_removal_requests TO devsync_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY removal_select ON member_removal_requests FOR SELECT TO devsync_app, devsync_worker
  USING (is_member_client(team_member_id) OR is_admin() OR is_system());
CREATE POLICY removal_write ON member_removal_requests FOR ALL TO devsync_app, devsync_worker
  USING (is_system()) WITH CHECK (is_system());
"""


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "lead_change_requests",
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("suggested_member_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REJECTED", "WITHDRAWN", name="lead_change_status"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
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
            "char_length(reason) BETWEEN 20 AND 500",
            name=op.f("ck_lead_change_requests_reason_length"),
        ),
        sa.CheckConstraint(
            "decision_reason IS NULL OR char_length(decision_reason) BETWEEN 20 AND 500",
            name=op.f("ck_lead_change_requests_decision_reason_length"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name=op.f("fk_lead_change_requests_decided_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_lead_change_requests_requested_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["suggested_member_id"],
            ["team_members.id"],
            name=op.f("fk_lead_change_requests_suggested_member_id_team_members"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_lead_change_requests_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_change_requests")),
    )
    op.create_index(
        "ix_lead_change_requests_team",
        "lead_change_requests",
        ["team_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "one_pending_lead_change_per_member",
        "lead_change_requests",
        ["team_id", "requested_by"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_table(
        "member_removal_requests",
        sa.Column("team_member_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("basis", sa.Enum("INACTIVITY", "DISPUTE", name="removal_basis"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REJECTED", name="removal_status"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
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
            "char_length(reason) BETWEEN 20 AND 500",
            name=op.f("ck_member_removal_requests_reason_length"),
        ),
        sa.CheckConstraint(
            "decision_reason IS NULL OR char_length(decision_reason) BETWEEN 20 AND 500",
            name=op.f("ck_member_removal_requests_decision_reason_length"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name=op.f("fk_member_removal_requests_decided_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_member_removal_requests_requested_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["team_member_id"],
            ["team_members.id"],
            name=op.f("fk_member_removal_requests_team_member_id_team_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_removal_requests")),
    )
    op.create_index(
        "ix_member_removal_requests_member",
        "member_removal_requests",
        ["team_member_id"],
        unique=False,
    )
    op.create_index(
        "one_pending_removal_per_member",
        "member_removal_requests",
        ["team_member_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_table(
        "repair_proposals",
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("departed_member_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "COMPUTING",
                "READY",
                "NO_CANDIDATES",
                "CHOSEN",
                "SUPERSEDED",
                "CANCELLED",
                name="repair_status",
            ),
            server_default="COMPUTING",
            nullable=False,
        ),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("impact", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("chosen_bid_id", sa.UUID(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint("seed >= 0", name=op.f("ck_repair_proposals_seed_non_negative")),
        sa.ForeignKeyConstraint(
            ["chosen_bid_id"], ["bids.id"], name=op.f("fk_repair_proposals_chosen_bid_id_bids")
        ),
        sa.ForeignKeyConstraint(
            ["departed_member_id"],
            ["team_members.id"],
            name=op.f("fk_repair_proposals_departed_member_id_team_members"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_repair_proposals_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_repair_proposals_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repair_proposals")),
    )
    op.create_index(
        "ix_repair_proposals_team", "repair_proposals", ["team_id", "created_at"], unique=False
    )
    op.create_index(
        "one_open_repair_per_departure",
        "repair_proposals",
        ["departed_member_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('COMPUTING', 'READY', 'NO_CANDIDATES')"),
    )
    op.add_column(
        "project_slots", sa.Column("reopened_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "project_slots",
        sa.Column("reopen_count", sa.SmallInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "team_members", sa.Column("lead_declined_at", sa.DateTime(timezone=True), nullable=True)
    )
    # ### end Alembic commands ###
    op.create_check_constraint(
        op.f("ck_project_slots_reopen_count_range"), "project_slots", "reopen_count BETWEEN 0 AND 2"
    )
    op.execute(HELPERS)
    for fn in NEW_HELPERS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, devsync_readonly")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {DML_ROLES}")
    op.execute(POLICIES)
    op.execute(f"REVOKE DELETE, TRUNCATE ON repair_proposals FROM {DML_ROLES}")


def downgrade() -> None:
    # Policies and the trigger go with their tables; then the helpers, enums and old definition.
    op.drop_constraint(op.f("ck_project_slots_reopen_count_range"), "project_slots", type_="check")
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("team_members", "lead_declined_at")
    op.drop_column("project_slots", "reopen_count")
    op.drop_column("project_slots", "reopened_until")
    op.drop_index(
        "one_open_repair_per_departure",
        table_name="repair_proposals",
        postgresql_where=sa.text("status IN ('COMPUTING', 'READY', 'NO_CANDIDATES')"),
    )
    op.drop_index("ix_repair_proposals_team", table_name="repair_proposals")
    op.drop_table("repair_proposals")
    op.drop_index(
        "one_pending_removal_per_member",
        table_name="member_removal_requests",
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.drop_index("ix_member_removal_requests_member", table_name="member_removal_requests")
    op.drop_table("member_removal_requests")
    op.drop_index(
        "one_pending_lead_change_per_member",
        table_name="lead_change_requests",
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.drop_index("ix_lead_change_requests_team", table_name="lead_change_requests")
    op.drop_table("lead_change_requests")
    # ### end Alembic commands ###
    for fn in (*NEW_HELPERS, "repair_proposal_guard()"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    op.execute(RESTORE_TEAM_MEMBER)
    for enum_name in ("removal_status", "removal_basis", "repair_status", "lead_change_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
