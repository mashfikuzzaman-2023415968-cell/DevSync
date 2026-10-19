"""Projects, slots, milestones, dependencies and plan baselines (Phase 4).

- Tables from spec §7.3 (projects, project_slots, milestones, milestone_skills,
  milestone_dependencies, plan_baselines, plan_change_requests).
- Row-level security on every new table (§14.15): a DRAFT project and its plan are visible only
  to the owning client and admins; once the project leaves DRAFT its project/slot/milestone rows
  are visible to everyone (the Phase 5 marketplace reads a limited-column view). Writes to a
  project and its plan are limited to the owning client. Two SECURITY DEFINER helpers,
  `is_project_client()` and `project_visible()`, keep the child-table policies readable and avoid
  RLS recursion on `projects`.
- Defense-in-depth triggers (the services enforce these too, §9.10/§8): a plan baseline's content
  is immutable once written, and a DRAFT→BIDDING publish requires milestone shares summing to
  100% and slot counts summing to the team size.

Revision ID: 0005_projects_planning
Revises: 0004_profiles_files_tests
Create Date: 2026-10-19 06:12:03.094250+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_projects_planning"
down_revision: str | None = "0004_profiles_files_tests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DML_ROLES = "devsync_app, devsync_worker"

# Helper functions used by the row-level-security policies. SECURITY DEFINER (owned by the
# migrator) so they can read `projects` without the caller's RLS, which also prevents the
# policy on `projects` from recursing when a child-table policy checks the parent project.
HELPERS = r"""
CREATE FUNCTION is_project_client(p_project uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL
     AND EXISTS (SELECT 1 FROM projects WHERE id = p_project AND client_id = app_uid())
$$;

CREATE FUNCTION project_visible(p_project uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT EXISTS (
    SELECT 1 FROM projects p
    WHERE p.id = p_project
      AND (p.status <> 'DRAFT' OR p.client_id = app_uid() OR is_admin())
  )
$$;
"""

TRIGGERS = r"""
-- A plan baseline's identity and plan are frozen once written (§7.3); only the approval flags
-- may change afterwards.
CREATE FUNCTION guard_baseline_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF NEW.project_id <> OLD.project_id OR NEW.version <> OLD.version
     OR NEW.cpm::text <> OLD.cpm::text OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
    RAISE EXCEPTION 'plan baseline content is immutable' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER plan_baselines_immutable BEFORE UPDATE ON plan_baselines
  FOR EACH ROW EXECUTE FUNCTION guard_baseline_immutable();

-- Publishing (DRAFT -> BIDDING) requires a complete plan: milestone shares total 100% and the
-- slot counts total the team size (spec §8 guard; the service checks this first).
CREATE FUNCTION guard_project_publish() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE
  v_share int;
  v_milestones int;
  v_slots int;
BEGIN
  IF NEW.status = 'BIDDING' AND OLD.status = 'DRAFT' THEN
    SELECT coalesce(sum(share_bp), 0), count(*) INTO v_share, v_milestones
      FROM milestones WHERE project_id = NEW.id;
    IF v_milestones = 0 OR v_share <> 10000 THEN
      RAISE EXCEPTION 'milestone shares must total 100%% before publishing'
        USING ERRCODE = 'check_violation';
    END IF;
    SELECT coalesce(sum(count), 0) INTO v_slots FROM project_slots WHERE project_id = NEW.id;
    IF v_slots <> NEW.team_size THEN
      RAISE EXCEPTION 'slot counts must total the team size before publishing'
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER projects_publish_guard BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION guard_project_publish();
"""

# Row-level security. `migrator_all` lets migrations and the definer-owner operate under FORCE
# RLS. A child milestone_skills row has no project_id, so its policies resolve the project via
# its milestone.
# DDL built only from fixed role names (no user input); roles inlined so there is no
# string-formatted SQL for the SQL-injection linter to flag.
POLICIES = """
-- projects: visible when not DRAFT, or to the owning client, or to admins; writes by the client.
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON projects TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY owner_select ON projects FOR SELECT TO devsync_app, devsync_worker
  USING (status <> 'DRAFT' OR client_id = app_uid() OR is_admin());
CREATE POLICY client_insert ON projects FOR INSERT TO devsync_app, devsync_worker
  WITH CHECK (client_id = app_uid() AND app_role() = 'CLIENT');
CREATE POLICY client_update ON projects FOR UPDATE TO devsync_app, devsync_worker
  USING (client_id = app_uid() OR is_admin())
  WITH CHECK (client_id = app_uid() OR is_admin());
CREATE POLICY client_delete ON projects FOR DELETE TO devsync_app, devsync_worker
  USING (client_id = app_uid());

-- project_slots / milestones / milestone_dependencies carry project_id directly.
ALTER TABLE project_slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_slots FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON project_slots TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY project_select ON project_slots FOR SELECT TO devsync_app, devsync_worker
  USING (project_visible(project_id));
CREATE POLICY client_write ON project_slots FOR ALL TO devsync_app, devsync_worker
  USING (is_project_client(project_id)) WITH CHECK (is_project_client(project_id));

ALTER TABLE milestones ENABLE ROW LEVEL SECURITY;
ALTER TABLE milestones FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON milestones TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY project_select ON milestones FOR SELECT TO devsync_app, devsync_worker
  USING (project_visible(project_id));
CREATE POLICY client_write ON milestones FOR ALL TO devsync_app, devsync_worker
  USING (is_project_client(project_id)) WITH CHECK (is_project_client(project_id));

ALTER TABLE milestone_dependencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE milestone_dependencies FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON milestone_dependencies TO devsync_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY project_select ON milestone_dependencies FOR SELECT TO devsync_app, devsync_worker
  USING (project_visible(project_id));
CREATE POLICY client_write ON milestone_dependencies FOR ALL TO devsync_app, devsync_worker
  USING (is_project_client(project_id)) WITH CHECK (is_project_client(project_id));

-- milestone_skills resolves its project through the milestone.
ALTER TABLE milestone_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE milestone_skills FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON milestone_skills TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY project_select ON milestone_skills FOR SELECT TO devsync_app, devsync_worker
  USING (project_visible((SELECT m.project_id FROM milestones m WHERE m.id = milestone_id)));
CREATE POLICY client_write ON milestone_skills FOR ALL TO devsync_app, devsync_worker
  USING (is_project_client((SELECT m.project_id FROM milestones m WHERE m.id = milestone_id)))
  WITH CHECK (is_project_client((SELECT m.project_id FROM milestones m WHERE m.id = milestone_id)));

-- plan_baselines / plan_change_requests: the owning client and admins only (not public).
ALTER TABLE plan_baselines ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_baselines FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON plan_baselines TO devsync_migrator USING (true) WITH CHECK (true);
CREATE POLICY client_select ON plan_baselines FOR SELECT TO devsync_app, devsync_worker
  USING (is_project_client(project_id) OR is_admin());
CREATE POLICY client_write ON plan_baselines FOR ALL TO devsync_app, devsync_worker
  USING (is_project_client(project_id)) WITH CHECK (is_project_client(project_id));

ALTER TABLE plan_change_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_change_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY migrator_all ON plan_change_requests TO devsync_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY client_select ON plan_change_requests FOR SELECT TO devsync_app, devsync_worker
  USING (is_project_client(project_id) OR is_admin());
CREATE POLICY client_write ON plan_change_requests FOR ALL TO devsync_app, devsync_worker
  USING (is_project_client(project_id)) WITH CHECK (is_project_client(project_id));
"""

HELPER_FUNCTIONS = ("is_project_client(uuid)", "project_visible(uuid)")
TRIGGER_FUNCTIONS = ("guard_baseline_immutable()", "guard_project_publish()")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("requirements", sa.Text(), server_default="", nullable=False),
        sa.Column("budget_paisa", sa.BigInteger(), nullable=False),
        sa.Column("bonus_pool_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("deadline_days", sa.SmallInteger(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("bidding_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("team_size", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "BIDDING",
                "FORMING",
                "TEAM_PENDING",
                "IN_PROGRESS",
                "ON_HOLD",
                "REVIEW_WINDOW",
                "COMPLETED",
                "CANCELLED",
                name="project_status",
            ),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repo_url", sa.Text(), nullable=True),
        sa.Column("settings_version", sa.Integer(), nullable=True),
        sa.Column("current_baseline_id", sa.UUID(), nullable=True),
        sa.Column("bidding_extensions", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
        sa.CheckConstraint("bidding_extensions >= 0", name=op.f("ck_projects_extensions_nonneg")),
        sa.CheckConstraint("bonus_pool_paisa >= 0", name=op.f("ck_projects_bonus_pool_nonneg")),
        sa.CheckConstraint("budget_paisa >= 0", name=op.f("ck_projects_budget_nonneg")),
        sa.CheckConstraint(
            "char_length(description) <= 10000", name=op.f("ck_projects_description_len")
        ),
        sa.CheckConstraint(
            "char_length(requirements) <= 5000", name=op.f("ck_projects_requirements_len")
        ),
        sa.CheckConstraint("char_length(summary) <= 300", name=op.f("ck_projects_summary_len")),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 5 AND 120", name=op.f("ck_projects_title_len")
        ),
        sa.CheckConstraint(
            "deadline_days BETWEEN 1 AND 365", name=op.f("ck_projects_deadline_range")
        ),
        sa.CheckConstraint("team_size BETWEEN 2 AND 10", name=op.f("ck_projects_team_size_range")),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["users.id"],
            name=op.f("fk_projects_client_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index("ix_projects_client_id", "projects", ["client_id"], unique=False)
    op.create_index(
        "ix_projects_status_bidding_deadline",
        "projects",
        ["status", "bidding_deadline"],
        unique=False,
    )
    op.create_table(
        "milestones",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("duration_days", sa.SmallInteger(), nullable=False),
        sa.Column("share_bp", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PLANNED",
                "FUNDED",
                "ACTIVE",
                "SUBMITTED",
                "APPROVED",
                "CHANGES_REQUESTED",
                "AUTO_APPROVED",
                "PAID",
                "DISPUTED",
                "REFUNDED",
                name="milestone_status",
            ),
            server_default="PLANNED",
            nullable=False,
        ),
        sa.Column("actual_start", sa.Date(), nullable=True),
        sa.Column("actual_finish", sa.Date(), nullable=True),
        sa.Column("revision_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_approve_at", sa.DateTime(timezone=True), nullable=True),
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
            "char_length(name) BETWEEN 1 AND 160", name=op.f("ck_milestones_name_len")
        ),
        sa.CheckConstraint("duration_days >= 1", name=op.f("ck_milestones_duration_positive")),
        sa.CheckConstraint("revision_count >= 0", name=op.f("ck_milestones_revision_nonneg")),
        sa.CheckConstraint("share_bp BETWEEN 0 AND 10000", name=op.f("ck_milestones_share_range")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_milestones_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestones")),
    )
    op.create_index(
        "ix_milestones_project_id_position", "milestones", ["project_id", "position"], unique=False
    )
    op.create_table(
        "plan_baselines",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("cpm", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("approved_by_client", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("approved_by_lead", sa.Boolean(), server_default="false", nullable=False),
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
            ["created_by"],
            ["users.id"],
            name=op.f("fk_plan_baselines_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_plan_baselines_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_baselines")),
        sa.UniqueConstraint("project_id", "version", name="project_version"),
    )
    op.create_index("ix_plan_baselines_project_id", "plan_baselines", ["project_id"], unique=False)
    op.create_table(
        "plan_change_requests",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("proposed_by", sa.UUID(), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REJECTED", name="plan_change_status"),
            server_default="PENDING",
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
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_plan_change_requests_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_by"],
            ["users.id"],
            name=op.f("fk_plan_change_requests_proposed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_change_requests")),
    )
    op.create_index(
        "ix_plan_change_requests_project_id", "plan_change_requests", ["project_id"], unique=False
    )
    op.create_table(
        "project_slots",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.Text(), server_default="", nullable=False),
        sa.Column("count", sa.SmallInteger(), server_default="1", nullable=False),
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
        sa.CheckConstraint("count >= 1", name=op.f("ck_project_slots_count_positive")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_slots_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_project_slots_skill_id_skills"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_slots")),
    )
    op.create_index("ix_project_slots_project_id", "project_slots", ["project_id"], unique=False)
    op.create_index("ix_project_slots_skill_id", "project_slots", ["skill_id"], unique=False)
    op.create_table(
        "milestone_dependencies",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("predecessor_id", sa.UUID(), nullable=False),
        sa.Column("successor_id", sa.UUID(), nullable=False),
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
            "predecessor_id <> successor_id", name=op.f("ck_milestone_dependencies_no_self_loop")
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_id"],
            ["milestones.id"],
            name=op.f("fk_milestone_dependencies_predecessor_id_milestones"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_milestone_dependencies_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["successor_id"],
            ["milestones.id"],
            name=op.f("fk_milestone_dependencies_successor_id_milestones"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestone_dependencies")),
        sa.UniqueConstraint("predecessor_id", "successor_id", name="edge"),
    )
    op.create_index(
        "ix_milestone_dependencies_predecessor_id",
        "milestone_dependencies",
        ["predecessor_id"],
        unique=False,
    )
    op.create_index(
        "ix_milestone_dependencies_project_id",
        "milestone_dependencies",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_milestone_dependencies_successor_id",
        "milestone_dependencies",
        ["successor_id"],
        unique=False,
    )
    op.create_table(
        "milestone_skills",
        sa.Column("milestone_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
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
            ["milestone_id"],
            ["milestones.id"],
            name=op.f("fk_milestone_skills_milestone_id_milestones"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_milestone_skills_skill_id_skills"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestone_skills")),
        sa.UniqueConstraint("milestone_id", "skill_id", name="milestone_skill"),
    )
    op.create_index(
        "ix_milestone_skills_milestone_id", "milestone_skills", ["milestone_id"], unique=False
    )
    op.create_index("ix_milestone_skills_skill_id", "milestone_skills", ["skill_id"], unique=False)

    # Helpers, triggers and RLS policies.
    op.execute(HELPERS)
    for fn in HELPER_FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, devsync_readonly")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {DML_ROLES}")
    op.execute(TRIGGERS)
    for fn in TRIGGER_FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, devsync_readonly")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {DML_ROLES}")
    op.execute(POLICIES)


def downgrade() -> None:
    # Drop the tables first: their RLS policies, triggers and indexes go with them, so the
    # helper and trigger functions they reference can then be dropped without CASCADE.
    op.drop_index("ix_milestone_skills_skill_id", table_name="milestone_skills")
    op.drop_index("ix_milestone_skills_milestone_id", table_name="milestone_skills")
    op.drop_table("milestone_skills")
    op.drop_index("ix_milestone_dependencies_successor_id", table_name="milestone_dependencies")
    op.drop_index("ix_milestone_dependencies_project_id", table_name="milestone_dependencies")
    op.drop_index("ix_milestone_dependencies_predecessor_id", table_name="milestone_dependencies")
    op.drop_table("milestone_dependencies")
    op.drop_index("ix_project_slots_skill_id", table_name="project_slots")
    op.drop_index("ix_project_slots_project_id", table_name="project_slots")
    op.drop_table("project_slots")
    op.drop_index("ix_plan_change_requests_project_id", table_name="plan_change_requests")
    op.drop_table("plan_change_requests")
    op.drop_index("ix_plan_baselines_project_id", table_name="plan_baselines")
    op.drop_table("plan_baselines")
    op.drop_index("ix_milestones_project_id_position", table_name="milestones")
    op.drop_table("milestones")
    op.drop_index("ix_projects_status_bidding_deadline", table_name="projects")
    op.drop_index("ix_projects_client_id", table_name="projects")
    op.drop_table("projects")
    for fn in (*TRIGGER_FUNCTIONS, *HELPER_FUNCTIONS):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    for enum_name in ("project_status", "milestone_status", "plan_change_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
