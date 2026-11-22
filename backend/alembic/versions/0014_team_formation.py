"""Team formation (Phase 7): runs, explanations, teams, members, invitations (spec §7.4).

- `formation_runs` keep each run's frozen inputs (params, seed, settings version, candidate
  snapshot) and its result. A trigger refuses any change to the inputs after insert and refuses
  deleting a run, so every run can be reproduced and audited (§14.13 row 7, FR-TEAM-6). Readable
  by the project's client and admins.
- `bid_explanations` ("why not selected") are readable only by the bidder and admins (sealed
  bids, §14.13 row 7).
- `teams`, `team_members`, `invitations` are created on confirm; invitations are recorded but not
  sent until Phase 8 (D108). Teams and members are readable by the project's client, the team's
  members and admins; an invitation by its invitee, the client and admins.
- Every write is SYSTEM-only (`is_system()`, the worker login role, D99): the services authorise
  the caller and then write in a SYSTEM session (D50 pattern).
- Definer helpers (`is_team_member`, `is_team_client`, `invitation_visible`,
  `is_bid_owner`) keep the policies from recursing into each other; `search_path` pinned.

Revision ID: 0014_team_formation
Revises: 0013_audit_chain_order
Create Date: 2026-11-22 14:18:10.409151+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_team_formation"
down_revision: str | None = "0013_audit_chain_order"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DML_ROLES = "devsync_app, devsync_worker"

HELPERS = r"""
CREATE FUNCTION is_team_member(p_team uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL
     AND EXISTS (SELECT 1 FROM team_members WHERE team_id = p_team AND developer_id = app_uid())
$$;

CREATE FUNCTION is_team_client(p_team uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT EXISTS (SELECT 1 FROM teams t WHERE t.id = p_team AND is_project_client(t.project_id))
$$;

CREATE FUNCTION invitation_visible(p_member uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL AND EXISTS (
    SELECT 1 FROM team_members m JOIN teams t ON t.id = m.team_id
    WHERE m.id = p_member AND (m.developer_id = app_uid() OR is_project_client(t.project_id))
  )
$$;

CREATE FUNCTION is_bid_owner(p_bid uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL
     AND EXISTS (SELECT 1 FROM bids WHERE id = p_bid AND developer_id = app_uid())
$$;

-- A run's inputs are frozen once written; only the result side changes, and runs are never
-- deleted (requested_by may still become NULL when an account is removed: ON DELETE SET NULL).
CREATE FUNCTION formation_run_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'formation runs are kept' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.project_id IS DISTINCT FROM OLD.project_id
     OR NEW.settings_version IS DISTINCT FROM OLD.settings_version
     OR NEW.seed IS DISTINCT FROM OLD.seed
     OR NEW.params IS DISTINCT FROM OLD.params
     OR NEW.candidate_snapshot IS DISTINCT FROM OLD.candidate_snapshot
     OR (NEW.requested_by IS DISTINCT FROM OLD.requested_by AND NEW.requested_by IS NOT NULL) THEN
    RAISE EXCEPTION 'a formation run''s inputs are immutable'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END;
$$;
"""
HELPER_FUNCTIONS = (
    "is_team_member(uuid)",
    "is_team_client(uuid)",
    "invitation_visible(uuid)",
    "is_bid_owner(uuid)",
)

POLICIES = """
ALTER TABLE formation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE formation_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON formation_runs TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY run_select ON formation_runs FOR SELECT TO devsync_app, devsync_worker
  USING (is_project_client(project_id) OR is_admin() OR is_system());
CREATE POLICY run_write ON formation_runs FOR ALL TO devsync_app, devsync_worker
  USING (is_system()) WITH CHECK (is_system());
CREATE TRIGGER formation_run_guard BEFORE UPDATE OR DELETE ON formation_runs
  FOR EACH ROW EXECUTE FUNCTION formation_run_guard();

ALTER TABLE bid_explanations ENABLE ROW LEVEL SECURITY;
ALTER TABLE bid_explanations FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON bid_explanations TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY explanation_select ON bid_explanations FOR SELECT TO devsync_app, devsync_worker
  USING (is_bid_owner(bid_id) OR is_admin() OR is_system());
CREATE POLICY explanation_write ON bid_explanations FOR ALL TO devsync_app, devsync_worker
  USING (is_system()) WITH CHECK (is_system());

ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON teams TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY team_select ON teams FOR SELECT TO devsync_app, devsync_worker
  USING (is_project_client(project_id) OR is_team_member(id) OR is_admin() OR is_system());
CREATE POLICY team_write ON teams FOR ALL TO devsync_app, devsync_worker
  USING (is_system()) WITH CHECK (is_system());

ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_members FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON team_members TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY member_select ON team_members FOR SELECT TO devsync_app, devsync_worker
  USING (developer_id = app_uid() OR is_team_member(team_id) OR is_team_client(team_id)
         OR is_admin() OR is_system());
CREATE POLICY member_write ON team_members FOR ALL TO devsync_app, devsync_worker
  USING (is_system()) WITH CHECK (is_system());

ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE invitations FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON invitations TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY invitation_select ON invitations FOR SELECT TO devsync_app, devsync_worker
  USING (invitation_visible(team_member_id) OR is_admin() OR is_system());
CREATE POLICY invitation_write ON invitations FOR ALL TO devsync_app, devsync_worker
  USING (is_system()) WITH CHECK (is_system());
"""


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "formation_runs",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "RUNNING",
                "SUCCEEDED",
                "INFEASIBLE",
                "FAILED",
                "TIMED_OUT",
                name="run_status",
            ),
            server_default="QUEUED",
            nullable=False,
        ),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("runtime_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            "char_length(error_code) <= 64", name=op.f("ck_formation_runs_error_code_length")
        ),
        sa.CheckConstraint(
            "runtime_ms IS NULL OR runtime_ms >= 0",
            name=op.f("ck_formation_runs_runtime_non_negative"),
        ),
        sa.CheckConstraint("seed >= 0", name=op.f("ck_formation_runs_seed_non_negative")),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_formation_runs_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_formation_runs_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_formation_runs_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formation_runs")),
    )
    op.create_index("ix_formation_runs_job", "formation_runs", ["job_id"], unique=False)
    op.create_index(
        "ix_formation_runs_project_created",
        "formation_runs",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "teams",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ACTIVE", "COMPLETED", "CANCELLED", name="team_status"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_teams_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["formation_runs.id"], name=op.f("fk_teams_run_id_formation_runs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("project_id", name=op.f("uq_teams_project_id")),
    )
    op.create_index("ix_teams_run", "teams", ["run_id"], unique=False)
    op.create_table(
        "bid_explanations",
        sa.Column("bid_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("price_counterfactual_paisa", sa.BigInteger(), nullable=True),
        sa.Column("main_gap", sa.Text(), nullable=True),
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
            "main_gap IS NULL OR main_gap IN ('comp', 'team', 'time', 'cost')",
            name=op.f("ck_bid_explanations_main_gap_known"),
        ),
        sa.CheckConstraint(
            "price_counterfactual_paisa IS NULL OR price_counterfactual_paisa > 0",
            name=op.f("ck_bid_explanations_counterfactual_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name=op.f("fk_bid_explanations_bid_id_bids")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["formation_runs.id"],
            name=op.f("fk_bid_explanations_run_id_formation_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bid_explanations")),
        sa.UniqueConstraint("bid_id", "run_id", name="uq_bid_explanations_bid_run"),
    )
    op.create_index("ix_bid_explanations_run", "bid_explanations", ["run_id"], unique=False)
    op.create_table(
        "team_members",
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("developer_id", sa.UUID(), nullable=False),
        sa.Column("bid_id", sa.UUID(), nullable=False),
        sa.Column("slot_id", sa.UUID(), nullable=False),
        sa.Column("price_paisa", sa.BigInteger(), nullable=False),
        sa.Column("days_needed", sa.SmallInteger(), nullable=False),
        sa.Column("is_lead", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "INVITED",
                "ACTIVE",
                "DECLINED",
                "EXPIRED",
                "COMPLETED",
                "LEFT",
                "REMOVED",
                name="member_status",
            ),
            server_default="INVITED",
            nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_reason", sa.Text(), nullable=True),
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
            "char_length(left_reason) <= 500", name=op.f("ck_team_members_left_reason_length")
        ),
        sa.CheckConstraint("days_needed >= 1", name=op.f("ck_team_members_days_positive")),
        sa.CheckConstraint("price_paisa >= 0", name=op.f("ck_team_members_price_non_negative")),
        sa.ForeignKeyConstraint(["bid_id"], ["bids.id"], name=op.f("fk_team_members_bid_id_bids")),
        sa.ForeignKeyConstraint(
            ["developer_id"], ["users.id"], name=op.f("fk_team_members_developer_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["slot_id"], ["project_slots.id"], name=op.f("fk_team_members_slot_id_project_slots")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_team_members_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_members")),
        sa.UniqueConstraint("bid_id", name=op.f("uq_team_members_bid_id")),
        sa.UniqueConstraint("team_id", "developer_id", name="uq_team_members_team_developer"),
    )
    op.create_index("ix_team_members_developer", "team_members", ["developer_id"], unique=False)
    op.create_index("ix_team_members_slot", "team_members", ["slot_id"], unique=False)
    op.create_index(
        "one_active_lead_per_team",
        "team_members",
        ["team_id"],
        unique=True,
        postgresql_where=sa.text("is_lead AND status = 'ACTIVE'"),
    )
    op.create_table(
        "invitations",
        sa.Column("team_member_id", sa.UUID(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "response",
            sa.Enum("ACCEPTED", "DECLINED", "EXPIRED", name="invitation_response"),
            nullable=True,
        ),
        sa.Column("is_replacement", sa.Boolean(), server_default="false", nullable=False),
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
            "(responded_at IS NULL) = (response IS NULL)",
            name=op.f("ck_invitations_response_iff_answered"),
        ),
        sa.CheckConstraint(
            "(sent_at IS NULL) = (expires_at IS NULL)", name=op.f("ck_invitations_expiry_iff_sent")
        ),
        sa.ForeignKeyConstraint(
            ["team_member_id"],
            ["team_members.id"],
            name=op.f("fk_invitations_team_member_id_team_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("team_member_id", name=op.f("uq_invitations_team_member_id")),
    )
    # ### end Alembic commands ###

    op.execute(HELPERS)
    for fn in HELPER_FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, devsync_readonly")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {DML_ROLES}")
    op.execute(POLICIES)
    # Runs are records: no deleting for the runtime roles (the trigger refuses it too).
    op.execute(f"REVOKE DELETE, TRUNCATE ON formation_runs FROM {DML_ROLES}")


def downgrade() -> None:
    # Policies and the trigger go with their tables; then the helpers and the enum types.
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("invitations")
    op.drop_index(
        "one_active_lead_per_team",
        table_name="team_members",
        postgresql_where=sa.text("is_lead AND status = 'ACTIVE'"),
    )
    op.drop_index("ix_team_members_slot", table_name="team_members")
    op.drop_index("ix_team_members_developer", table_name="team_members")
    op.drop_table("team_members")
    op.drop_index("ix_bid_explanations_run", table_name="bid_explanations")
    op.drop_table("bid_explanations")
    op.drop_index("ix_teams_run", table_name="teams")
    op.drop_table("teams")
    op.drop_index("ix_formation_runs_project_created", table_name="formation_runs")
    op.drop_index("ix_formation_runs_job", table_name="formation_runs")
    op.drop_table("formation_runs")
    # ### end Alembic commands ###
    for fn in (*HELPER_FUNCTIONS, "formation_run_guard()"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    for enum_name in ("invitation_response", "member_status", "team_status", "run_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
