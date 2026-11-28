"""Workspace and monitoring (Phase 9): spec §7.5, §7.8, §14.15; D141–D173.

- Tables: tasks, task_dependencies, task_evidence, comments (+ revisions), discussion threads and
  posts (+ revisions), checkins, activity_events (append-only), risks, forecast_snapshots,
  notification_preferences; `files` gains `project_id` and the kind PROJECT_FILE (D147).
- Helpers (§14.15): `is_project_member` (ACTIVE, or COMPLETED for reading), `is_active_project_member`
  (writes), `is_participant` (client or member), `is_project_lead`, `is_own_member`; all STABLE
  definers with a pinned `search_path`.
- `record_activity()` (D149): the only way a web request writes an evidence event. The actor is
  the caller (`app_uid()`), never a parameter; the caller must be a participant; the type must be
  in the §9.1.6 catalogue. SYSTEM paths insert directly.
- Every workspace row's `project_id` must match its parent and never changes (D166); dependencies
  stay inside one milestone; evidence files are live project files of the same project (D168).
- Check-ins, task evidence and activity events are append-only (`reject_mutation`); comment and
  post edits keep the old body in revision tables only admins read (D169).
- RLS (ENABLE + FORCE everywhere): participants read; ACTIVE members write within §2.2 (the
  services narrow further, D142); risks hide BUDGET and AUTO_APPROVAL_SOON from members (D151);
  risks, snapshots and events are SYSTEM-written; preferences are own rows (+ SYSTEM reads).
- `file_access()`: a project file is readable by its project's participants and SYSTEM only; the
  owner loses access on leaving and admins get it with Phase 12's disputes (D142, D173).
- Settings v6 adds `ratelimit.upload_bytes_per_day` (§14.8 500 MB/day).

Revision ID: 0016_workspace
Revises: 0015_team_lifecycle
Create Date: 2026-11-27 06:15:52.813834+00:00
"""

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_workspace"
down_revision: str | None = "0015_team_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DML_ROLES = "devsync_app, devsync_worker"
SEED_DIR = Path(__file__).resolve().parents[1] / "seed"
SETTINGS_V6 = SEED_DIR / "platform_settings_v6.json"

ACTIVITY_TYPES = (
    "'checkin.posted', 'checkin.missed', 'comment.posted', 'comment.replied', 'task.moved', "
    "'task.done', 'task.reopened', 'task.evidence_added', 'milestone.submitted', "
    "'milestone.approved', 'milestone.changes_requested', 'milestone.auto_approved', "
    "'work.started', 'blocker.reported', 'blocker.answered', 'github.pr_merged', "
    "'github.review_given', 'split.proposed', 'split.agreed', 'split.objected', 'member.left', "
    "'member.replaced'"
)

HELPERS = r"""
CREATE FUNCTION is_project_member(p_project uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL
     AND EXISTS (SELECT 1 FROM team_members m JOIN teams t ON t.id = m.team_id
                 WHERE t.project_id = p_project AND m.developer_id = app_uid()
                   AND m.status IN ('ACTIVE', 'COMPLETED'))
$$;

CREATE FUNCTION is_active_project_member(p_project uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL
     AND EXISTS (SELECT 1 FROM team_members m JOIN teams t ON t.id = m.team_id
                 WHERE t.project_id = p_project AND m.developer_id = app_uid()
                   AND m.status = 'ACTIVE')
$$;

CREATE FUNCTION is_participant(p_project uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT is_project_client(p_project) OR is_project_member(p_project)
$$;

CREATE FUNCTION is_project_lead(p_project uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL
     AND EXISTS (SELECT 1 FROM team_members m JOIN teams t ON t.id = m.team_id
                 WHERE t.project_id = p_project AND m.developer_id = app_uid()
                   AND m.status = 'ACTIVE' AND m.is_lead)
$$;

CREATE FUNCTION is_own_member(p_member uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT app_uid() IS NOT NULL
     AND EXISTS (SELECT 1 FROM team_members WHERE id = p_member AND developer_id = app_uid()
                 AND status = 'ACTIVE')
$$;
"""
HELPER_NAMES = (
    "is_project_member(uuid)",
    "is_active_project_member(uuid)",
    "is_participant(uuid)",
    "is_project_lead(uuid)",
    "is_own_member(uuid)",
)

# The definer that records evidence for a web request (D149). `p_at` is the service clock's
# "now" (every timestamp the services write comes from it, so seeded history has its true time).
RECORD_ACTIVITY_TEMPLATE = r"""
CREATE FUNCTION record_activity(p_project uuid, p_type text, p_entity_type text,
                                p_entity_id uuid, p_subject uuid, p_data jsonb, p_at timestamptz)
RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_id uuid;
BEGIN
  IF app_uid() IS NULL OR NOT is_participant(p_project) THEN
    RAISE EXCEPTION 'only a participant of the project records its activity'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF p_type IS NULL OR p_type NOT IN (__ACTIVITY_TYPES__) THEN
    RAISE EXCEPTION 'unknown activity type' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF p_subject IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM projects p WHERE p.id = p_project AND p.client_id = p_subject
       UNION ALL
       SELECT 1 FROM team_members m JOIN teams t ON t.id = m.team_id
       WHERE t.project_id = p_project AND m.developer_id = p_subject) THEN
    RAISE EXCEPTION 'the subject is not part of the project'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO activity_events (project_id, actor_id, subject_id, type, entity_type, entity_id,
                               data, at)
  VALUES (p_project, app_uid(), p_subject, p_type, p_entity_type, p_entity_id,
          coalesce(p_data, '{}'::jsonb), coalesce(p_at, now()))
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;
"""
RECORD_ACTIVITY = RECORD_ACTIVITY_TEMPLATE.replace("__ACTIVITY_TYPES__", ACTIVITY_TYPES)
RECORD_ACTIVITY_SIG = "record_activity(uuid, text, text, uuid, uuid, jsonb, timestamptz)"

TRIGGERS = r"""
-- D166: a workspace row's project is its parent's, and never changes.
CREATE FUNCTION workspace_project_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  expected uuid;
  m1 uuid;
  m2 uuid;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.project_id IS DISTINCT FROM OLD.project_id THEN
    RAISE EXCEPTION 'a workspace row never changes project' USING ERRCODE = 'check_violation';
  END IF;
  IF TG_TABLE_NAME = 'tasks' THEN
    SELECT project_id INTO expected FROM milestones WHERE id = NEW.milestone_id;
  ELSIF TG_TABLE_NAME = 'task_dependencies' THEN
    SELECT project_id, milestone_id INTO expected, m1 FROM tasks WHERE id = NEW.task_id;
    SELECT milestone_id INTO m2 FROM tasks WHERE id = NEW.depends_on_task_id;
    IF m1 IS DISTINCT FROM m2 THEN
      RAISE EXCEPTION 'dependencies stay inside one milestone' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF TG_TABLE_NAME = 'task_evidence' THEN
    SELECT project_id INTO expected FROM tasks WHERE id = NEW.task_id;
    IF NEW.file_id IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM files f WHERE f.id = NEW.file_id AND f.project_id = expected
           AND f.kind::text = 'PROJECT_FILE' AND f.deleted_at IS NULL
           AND (NEW.kind::text <> 'SCREENSHOT' OR f.mime_type LIKE 'image/%')) THEN
      RAISE EXCEPTION 'evidence files are live project files of the same project'
        USING ERRCODE = 'check_violation';
    END IF;
  ELSIF TG_TABLE_NAME = 'comments' THEN
    IF NEW.target_type::text = 'TASK' THEN
      SELECT project_id INTO expected FROM tasks WHERE id = NEW.target_id;
    ELSIF NEW.target_type::text = 'MILESTONE' THEN
      SELECT project_id INTO expected FROM milestones WHERE id = NEW.target_id;
    ELSE
      SELECT project_id INTO expected FROM checkins WHERE id = NEW.target_id;
    END IF;
    IF NEW.reply_to_id IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM comments c WHERE c.id = NEW.reply_to_id
           AND c.target_type = NEW.target_type AND c.target_id = NEW.target_id) THEN
      RAISE EXCEPTION 'a reply stays on the same target' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF TG_TABLE_NAME = 'checkins' THEN
    SELECT t.project_id INTO expected FROM team_members m JOIN teams t ON t.id = m.team_id
    WHERE m.id = NEW.team_member_id;
  ELSIF TG_TABLE_NAME = 'discussion_posts' THEN
    SELECT project_id INTO expected FROM discussion_threads WHERE id = NEW.thread_id;
    IF NEW.reply_to_id IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM discussion_posts p WHERE p.id = NEW.reply_to_id
           AND p.thread_id = NEW.thread_id) THEN
      RAISE EXCEPTION 'a reply stays in the same thread' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF expected IS NULL OR expected <> NEW.project_id THEN
    RAISE EXCEPTION 'project_id does not match its parent' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

-- D169: an edit keeps the earlier body; who wrote it, where, and when never change.
CREATE FUNCTION comment_revision_capture() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  IF (NEW.author_id, NEW.created_at, NEW.reply_to_id, NEW.mentions)
     IS DISTINCT FROM (OLD.author_id, OLD.created_at, OLD.reply_to_id, OLD.mentions) THEN
    RAISE EXCEPTION 'only the text of a comment can change' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'a deleted comment stays deleted' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.body IS DISTINCT FROM OLD.body THEN
    IF TG_TABLE_NAME = 'comments' THEN
      IF (NEW.target_type, NEW.target_id) IS DISTINCT FROM (OLD.target_type, OLD.target_id) THEN
        RAISE EXCEPTION 'a comment never moves' USING ERRCODE = 'check_violation';
      END IF;
      INSERT INTO comment_revisions (comment_id, body) VALUES (OLD.id, OLD.body);
    ELSE
      INSERT INTO discussion_post_revisions (post_id, body) VALUES (OLD.id, OLD.body);
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

-- A new post moves its thread to the top for everyone (posters can't update others' threads).
CREATE FUNCTION thread_last_post() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  UPDATE discussion_threads SET last_post_at = greatest(last_post_at, NEW.created_at)
  WHERE id = NEW.thread_id;
  RETURN NULL;
END;
$$;

CREATE TRIGGER tasks_project BEFORE INSERT OR UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION workspace_project_guard();
CREATE TRIGGER task_dependencies_project BEFORE INSERT OR UPDATE ON task_dependencies
  FOR EACH ROW EXECUTE FUNCTION workspace_project_guard();
CREATE TRIGGER task_evidence_project BEFORE INSERT ON task_evidence
  FOR EACH ROW EXECUTE FUNCTION workspace_project_guard();
CREATE TRIGGER comments_project BEFORE INSERT OR UPDATE ON comments
  FOR EACH ROW EXECUTE FUNCTION workspace_project_guard();
CREATE TRIGGER checkins_project BEFORE INSERT ON checkins
  FOR EACH ROW EXECUTE FUNCTION workspace_project_guard();
CREATE TRIGGER discussion_posts_project BEFORE INSERT OR UPDATE ON discussion_posts
  FOR EACH ROW EXECUTE FUNCTION workspace_project_guard();
CREATE TRIGGER comments_revision BEFORE UPDATE ON comments
  FOR EACH ROW EXECUTE FUNCTION comment_revision_capture();
CREATE TRIGGER discussion_posts_revision BEFORE UPDATE ON discussion_posts
  FOR EACH ROW EXECUTE FUNCTION comment_revision_capture();
CREATE TRIGGER discussion_posts_thread AFTER INSERT ON discussion_posts
  FOR EACH ROW EXECUTE FUNCTION thread_last_post();
CREATE TRIGGER checkins_append_only BEFORE UPDATE OR DELETE ON checkins
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER task_evidence_append_only BEFORE UPDATE OR DELETE ON task_evidence
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER activity_events_append_only BEFORE UPDATE OR DELETE ON activity_events
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER activity_events_no_truncate BEFORE TRUNCATE ON activity_events
  FOR EACH STATEMENT EXECUTE FUNCTION reject_mutation();
"""
TRIGGER_FUNCTIONS = (
    "workspace_project_guard()",
    "comment_revision_capture()",
    "thread_last_post()",
)

# D147/D142/D173: project files are for the project's participants (and SYSTEM) only.
FILE_ACCESS_0016 = r"""
CREATE OR REPLACE FUNCTION file_access(p_file uuid)
RETURNS TABLE (storage_key uuid, mime_type text, original_name text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT f.storage_key, f.mime_type, f.original_name
  FROM files f
  WHERE f.id = p_file AND f.deleted_at IS NULL
    AND CASE WHEN f.kind::text = 'PROJECT_FILE'
          THEN caller_is_system() OR is_participant(f.project_id)
          ELSE f.owner_id = app_uid() OR is_admin() OR caller_is_system()
               OR (f.kind::text = 'PORTFOLIO_IMAGE'
                   AND EXISTS (SELECT 1 FROM portfolio_images pi WHERE pi.file_id = f.id)
                   AND profile_visible(f.owner_id))
        END
$$;

CREATE OR REPLACE FUNCTION files_identity_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF (NEW.owner_id, NEW.kind, NEW.storage_key, NEW.mime_type, NEW.size_bytes, NEW.sha256,
      NEW.width, NEW.height, NEW.original_name, NEW.project_id)
     IS DISTINCT FROM (OLD.owner_id, OLD.kind, OLD.storage_key, OLD.mime_type, OLD.size_bytes,
                       OLD.sha256, OLD.width, OLD.height, OLD.original_name, OLD.project_id) THEN
    RAISE EXCEPTION 'stored files are immutable' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT (is_admin() OR is_system()) AND NEW.scan_status IS DISTINCT FROM OLD.scan_status THEN
    RAISE EXCEPTION 'scan status is set by the scanner' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS DISTINCT FROM OLD.deleted_at THEN
    RAISE EXCEPTION 'a deleted file stays deleted' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END;
$$;
"""

# 0004's definitions, restored by the downgrade.
FILE_ACCESS_0004 = r"""
CREATE OR REPLACE FUNCTION file_access(p_file uuid)
RETURNS TABLE (storage_key uuid, mime_type text, original_name text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT f.storage_key, f.mime_type, f.original_name
  FROM files f
  WHERE f.id = p_file AND f.deleted_at IS NULL
    AND (f.owner_id = app_uid() OR is_admin() OR caller_is_system()
         OR (f.kind = 'PORTFOLIO_IMAGE'
             AND EXISTS (SELECT 1 FROM portfolio_images pi WHERE pi.file_id = f.id)
             AND profile_visible(f.owner_id)))
$$;

CREATE OR REPLACE FUNCTION files_identity_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF (NEW.owner_id, NEW.kind, NEW.storage_key, NEW.mime_type, NEW.size_bytes, NEW.sha256,
      NEW.width, NEW.height, NEW.original_name)
     IS DISTINCT FROM (OLD.owner_id, OLD.kind, OLD.storage_key, OLD.mime_type, OLD.size_bytes,
                       OLD.sha256, OLD.width, OLD.height, OLD.original_name) THEN
    RAISE EXCEPTION 'stored files are immutable' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT (is_admin() OR is_system()) AND NEW.scan_status IS DISTINCT FROM OLD.scan_status THEN
    RAISE EXCEPTION 'scan status is set by the scanner' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END;
$$;
"""

PROTECTED = (
    "tasks",
    "task_dependencies",
    "task_evidence",
    "comments",
    "comment_revisions",
    "discussion_threads",
    "discussion_posts",
    "discussion_post_revisions",
    "checkins",
    "activity_events",
    "risks",
    "forecast_snapshots",
    "notification_preferences",
)
READ = "is_participant(project_id) OR is_admin() OR is_system()"
MEMBER_WRITE = "is_active_project_member(project_id) OR is_system()"
POLICIES = f"""
CREATE POLICY ws_select ON tasks FOR SELECT TO {DML_ROLES} USING ({READ});
CREATE POLICY ws_insert ON tasks FOR INSERT TO {DML_ROLES} WITH CHECK ({MEMBER_WRITE});
CREATE POLICY ws_update ON tasks FOR UPDATE TO {DML_ROLES}
  USING ({MEMBER_WRITE}) WITH CHECK ({MEMBER_WRITE});
CREATE POLICY ws_delete ON tasks FOR DELETE TO {DML_ROLES} USING ({MEMBER_WRITE});

CREATE POLICY ws_select ON task_dependencies FOR SELECT TO {DML_ROLES} USING ({READ});
CREATE POLICY ws_insert ON task_dependencies FOR INSERT TO {DML_ROLES}
  WITH CHECK ({MEMBER_WRITE});
CREATE POLICY ws_delete ON task_dependencies FOR DELETE TO {DML_ROLES} USING ({MEMBER_WRITE});

CREATE POLICY ws_select ON task_evidence FOR SELECT TO {DML_ROLES} USING ({READ});
CREATE POLICY ws_insert ON task_evidence FOR INSERT TO {DML_ROLES}
  WITH CHECK ((is_active_project_member(project_id) AND added_by = app_uid()) OR is_system());

CREATE POLICY ws_select ON comments FOR SELECT TO {DML_ROLES}
  USING (is_participant(project_id) OR is_system());
CREATE POLICY ws_insert ON comments FOR INSERT TO {DML_ROLES}
  WITH CHECK ((is_participant(project_id) AND author_id = app_uid()) OR is_system());
CREATE POLICY ws_update ON comments FOR UPDATE TO {DML_ROLES}
  USING ((author_id = app_uid() AND is_participant(project_id)) OR is_system())
  WITH CHECK ((author_id = app_uid() AND is_participant(project_id)) OR is_system());

CREATE POLICY ws_select ON discussion_threads FOR SELECT TO {DML_ROLES}
  USING (is_participant(project_id) OR is_system());
CREATE POLICY ws_insert ON discussion_threads FOR INSERT TO {DML_ROLES}
  WITH CHECK ((is_participant(project_id) AND created_by = app_uid()) OR is_system());

CREATE POLICY ws_select ON discussion_posts FOR SELECT TO {DML_ROLES}
  USING (is_participant(project_id) OR is_system());
CREATE POLICY ws_insert ON discussion_posts FOR INSERT TO {DML_ROLES}
  WITH CHECK ((is_participant(project_id) AND author_id = app_uid()) OR is_system());
CREATE POLICY ws_update ON discussion_posts FOR UPDATE TO {DML_ROLES}
  USING ((author_id = app_uid() AND is_participant(project_id)) OR is_system())
  WITH CHECK ((author_id = app_uid() AND is_participant(project_id)) OR is_system());

CREATE POLICY admin_select ON comment_revisions FOR SELECT TO {DML_ROLES}
  USING (is_admin() OR is_system());
CREATE POLICY admin_select ON discussion_post_revisions FOR SELECT TO {DML_ROLES}
  USING (is_admin() OR is_system());

CREATE POLICY ws_select ON checkins FOR SELECT TO {DML_ROLES} USING ({READ});
CREATE POLICY ws_insert ON checkins FOR INSERT TO {DML_ROLES}
  WITH CHECK ((is_active_project_member(project_id) AND is_own_member(team_member_id))
              OR is_system());

CREATE POLICY ws_select ON activity_events FOR SELECT TO {DML_ROLES} USING ({READ});
CREATE POLICY system_insert ON activity_events FOR INSERT TO {DML_ROLES}
  WITH CHECK (is_system());

CREATE POLICY ws_select ON risks FOR SELECT TO {DML_ROLES}
  USING (is_project_client(project_id) OR is_admin() OR is_system()
         OR (is_project_member(project_id)
             AND type::text NOT IN ('BUDGET', 'AUTO_APPROVAL_SOON')));
CREATE POLICY system_write ON risks FOR ALL TO {DML_ROLES}
  USING (is_system()) WITH CHECK (is_system());

CREATE POLICY ws_select ON forecast_snapshots FOR SELECT TO {DML_ROLES} USING ({READ});
CREATE POLICY system_write ON forecast_snapshots FOR ALL TO {DML_ROLES}
  USING (is_system()) WITH CHECK (is_system());

CREATE POLICY own_select ON notification_preferences FOR SELECT TO {DML_ROLES}
  USING (user_id = app_uid() OR is_system());
CREATE POLICY own_write ON notification_preferences FOR ALL TO {DML_ROLES}
  USING (user_id = app_uid()) WITH CHECK (user_id = app_uid());
"""

FILE_POLICIES = f"""
-- The lead also sees deleted rows of the project: PostgreSQL checks an UPDATE's new row against
-- the SELECT policies, so without this a lead couldn't soft-delete a member's file (D175).
-- Listing and downloads still hide deleted files (the service and file_access()).
CREATE POLICY project_file_select ON files FOR SELECT TO {DML_ROLES}
  USING (project_id IS NOT NULL AND is_participant(project_id)
         AND (deleted_at IS NULL OR is_project_lead(project_id)));
CREATE POLICY project_file_delete ON files FOR UPDATE TO {DML_ROLES}
  USING (project_id IS NOT NULL AND is_project_lead(project_id))
  WITH CHECK (project_id IS NOT NULL AND is_project_lead(project_id));
CREATE POLICY project_file_guard ON files AS RESTRICTIVE FOR INSERT TO {DML_ROLES}
  WITH CHECK (project_id IS NULL OR is_participant(project_id) OR is_system());
"""
DROP_FILE_POLICIES = """
DROP POLICY IF EXISTS project_file_select ON files;
DROP POLICY IF EXISTS project_file_delete ON files;
DROP POLICY IF EXISTS project_file_guard ON files;
"""


def _rls() -> str:
    stmts: list[str] = []
    for table in PROTECTED:
        stmts += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY migrator_all ON {table} TO devsync_migrator "
            "USING (true) WITH CHECK (true)",
        ]
    return ";\n".join(stmts) + ";"


def upgrade() -> None:
    # The new enum value is committed on its own (D38: ADD VALUE can't be used in the
    # transaction that adds it); nothing below names it as an enum literal.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE file_kind ADD VALUE IF NOT EXISTS 'PROJECT_FILE'")
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("in_app", sa.Boolean(), nullable=False),
        sa.Column("email", sa.Boolean(), nullable=False),
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
            "type ~ '^[a-z_]{1,40}$'", name=op.f("ck_notification_preferences_type_format")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_preferences")),
        sa.UniqueConstraint("user_id", "type", name="uq_notification_preferences_user_type"),
    )
    op.create_table(
        "activity_events",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("subject_id", sa.UUID(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column(
            "data", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "type IN ('checkin.posted', 'checkin.missed', 'comment.posted', 'comment.replied', 'task.moved', 'task.done', 'task.reopened', 'task.evidence_added', 'milestone.submitted', 'milestone.approved', 'milestone.changes_requested', 'milestone.auto_approved', 'work.started', 'blocker.reported', 'blocker.answered', 'github.pr_merged', 'github.review_given', 'split.proposed', 'split.agreed', 'split.objected', 'member.left', 'member.replaced')",
            name=op.f("ck_activity_events_type_in_catalogue"),
        ),
        sa.CheckConstraint(
            "char_length(entity_type) BETWEEN 1 AND 40",
            name=op.f("ck_activity_events_entity_type_len"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_activity_events_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_activity_events_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["users.id"], name=op.f("fk_activity_events_subject_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activity_events")),
    )
    op.create_index(
        "ix_activity_events_project_actor",
        "activity_events",
        ["project_id", "actor_id", "type"],
        unique=False,
    )
    op.create_index(
        "ix_activity_events_project_at", "activity_events", ["project_id", "at"], unique=False
    )
    op.create_index(
        "ix_activity_events_project_subject",
        "activity_events",
        ["project_id", "subject_id", "type"],
        unique=False,
    )
    op.create_table(
        "comments",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "target_type",
            sa.Enum("TASK", "MILESTONE", "CHECKIN", name="comment_target"),
            nullable=False,
        ),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("mentions", postgresql.ARRAY(sa.UUID()), server_default="{}", nullable=False),
        sa.Column("reply_to_id", sa.UUID(), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("cardinality(mentions) <= 10", name=op.f("ck_comments_mentions_cap")),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 4000", name=op.f("ck_comments_body_len")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_comments_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_comments_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_id"], ["comments.id"], name=op.f("fk_comments_reply_to_id_comments")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )
    op.create_index("ix_comments_project", "comments", ["project_id", "created_at"], unique=False)
    op.create_index(
        "ix_comments_target",
        "comments",
        ["target_type", "target_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "discussion_threads",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "last_post_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
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
            "char_length(title) BETWEEN 3 AND 120", name=op.f("ck_discussion_threads_title_len")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_discussion_threads_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_discussion_threads_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discussion_threads")),
    )
    op.create_index(
        "ix_discussion_threads_project",
        "discussion_threads",
        ["project_id", sa.literal_column("last_post_at DESC"), "id"],
        unique=False,
    )
    op.create_table(
        "forecast_snapshots",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("forecast", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("impact_days", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
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
            name=op.f("fk_forecast_snapshots_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forecast_snapshots")),
        sa.UniqueConstraint("project_id", "day", name="uq_forecast_snapshots_project_day"),
    )
    op.create_table(
        "risks",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "CRITICAL_PATH_DELAY",
                "SLACK_EATEN",
                "DEADLINE_IMPACT",
                "SKILL_DEPENDENCY",
                "CAPACITY",
                "BUDGET",
                "STALLED_TASK",
                "INACTIVE_MEMBER",
                "AUTO_APPROVAL_SOON",
                name="risk_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "severity", sa.Enum("CRITICAL", "MEDIUM", "LOW", name="risk_severity"), nullable=False
        ),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "detail", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum("OPEN", "RESOLVED", name="risk_status"),
            server_default="OPEN",
            nullable=False,
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
            "(status = 'RESOLVED') = (resolved_at IS NOT NULL)", name=op.f("ck_risks_resolved_iff")
        ),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 200", name=op.f("ck_risks_title_len")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_risks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risks")),
    )
    op.create_index(
        "ix_risks_project_status_severity",
        "risks",
        ["project_id", "status", "severity"],
        unique=False,
    )
    op.create_index(
        "one_open_risk_per_entity",
        "risks",
        [
            "project_id",
            "type",
            "entity_type",
            sa.literal_column("coalesce(entity_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
        ],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
    )
    op.create_table(
        "comment_revisions",
        sa.Column("comment_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
            ["comment_id"],
            ["comments.id"],
            name=op.f("fk_comment_revisions_comment_id_comments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comment_revisions")),
    )
    op.create_index(
        op.f("ix_comment_revisions_comment_id"), "comment_revisions", ["comment_id"], unique=False
    )
    op.create_table(
        "discussion_posts",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("mentions", postgresql.ARRAY(sa.UUID()), server_default="{}", nullable=False),
        sa.Column("reply_to_id", sa.UUID(), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "cardinality(mentions) <= 10", name=op.f("ck_discussion_posts_mentions_cap")
        ),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 4000", name=op.f("ck_discussion_posts_body_len")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_discussion_posts_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_discussion_posts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_id"],
            ["discussion_posts.id"],
            name=op.f("fk_discussion_posts_reply_to_id_discussion_posts"),
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["discussion_threads.id"],
            name=op.f("fk_discussion_posts_thread_id_discussion_threads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discussion_posts")),
    )
    op.create_index(
        "ix_discussion_posts_thread",
        "discussion_posts",
        ["thread_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "tasks",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("milestone_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("assignee_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("TODO", "IN_PROGRESS", "REVIEW", "DONE", name="task_status"),
            server_default="TODO",
            nullable=False,
        ),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("estimate_hours", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column(
            "difficulty", sa.Enum("EASY", "MEDIUM", "HARD", name="task_difficulty"), nullable=False
        ),
        sa.Column("position", sa.Text(collation="C"), nullable=False),
        sa.Column("progress_pct", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=False),
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
        sa.CheckConstraint(
            "(status = 'TODO' AND progress_pct = 0) OR (status = 'IN_PROGRESS' AND progress_pct = 50) OR (status = 'REVIEW' AND progress_pct = 85) OR (status = 'DONE' AND progress_pct = 100)",
            name=op.f("ck_tasks_progress_matches_status"),
        ),
        sa.CheckConstraint(
            "position ~ '^[0-9A-Za-z]{1,64}$'", name=op.f("ck_tasks_position_format")
        ),
        sa.CheckConstraint(
            "char_length(description) <= 5000", name=op.f("ck_tasks_description_len")
        ),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 160", name=op.f("ck_tasks_title_len")),
        sa.CheckConstraint(
            "estimate_hours > 0 AND estimate_hours <= 999.9", name=op.f("ck_tasks_estimate_range")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_tasks_version_positive")),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["users.id"], name=op.f("fk_tasks_assignee_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_tasks_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"],
            ["milestones.id"],
            name=op.f("fk_tasks_milestone_id_milestones"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_tasks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(
        "ix_tasks_milestone_status_position",
        "tasks",
        ["milestone_id", "status", "position"],
        unique=False,
    )
    op.create_index(
        "ix_tasks_project_assignee", "tasks", ["project_id", "assignee_id"], unique=False
    )
    op.create_table(
        "discussion_post_revisions",
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
            ["post_id"],
            ["discussion_posts.id"],
            name=op.f("fk_discussion_post_revisions_post_id_discussion_posts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discussion_post_revisions")),
    )
    op.create_index(
        op.f("ix_discussion_post_revisions_post_id"),
        "discussion_post_revisions",
        ["post_id"],
        unique=False,
    )
    op.create_table(
        "task_dependencies",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("depends_on_task_id", sa.UUID(), nullable=False),
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
            "task_id <> depends_on_task_id", name=op.f("ck_task_dependencies_not_self")
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_task_id"],
            ["tasks.id"],
            name=op.f("fk_task_dependencies_depends_on_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_task_dependencies_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_dependencies_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_dependencies")),
        sa.UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies_pair"),
    )
    op.create_index(
        "ix_task_dependencies_depends_on", "task_dependencies", ["depends_on_task_id"], unique=False
    )
    op.create_table(
        "task_evidence",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("FILE", "LINK", "PR", "SCREENSHOT", name="evidence_kind"),
            nullable=False,
        ),
        sa.Column("file_id", sa.UUID(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("added_by", sa.UUID(), nullable=False),
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
            "(kind IN ('FILE', 'SCREENSHOT') AND file_id IS NOT NULL AND url IS NULL) OR (kind IN ('LINK', 'PR') AND url IS NOT NULL AND file_id IS NULL)",
            name=op.f("ck_task_evidence_kind_shape"),
        ),
        sa.CheckConstraint(
            "kind <> 'PR' OR url ~ '^https://github\\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[0-9]+$'",
            name=op.f("ck_task_evidence_pr_format"),
        ),
        sa.CheckConstraint(
            "url IS NULL OR (char_length(url) <= 2048 AND url ~ '^https://')",
            name=op.f("ck_task_evidence_url_https"),
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) <= 500", name=op.f("ck_task_evidence_note_len")
        ),
        sa.ForeignKeyConstraint(
            ["added_by"], ["users.id"], name=op.f("fk_task_evidence_added_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name=op.f("fk_task_evidence_file_id_files")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_task_evidence_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_task_evidence_task_id_tasks")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_evidence")),
    )
    op.create_index(
        "ix_task_evidence_task", "task_evidence", ["task_id", "created_at"], unique=False
    )
    op.create_table(
        "checkins",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("team_member_id", sa.UUID(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("done", sa.Text(), nullable=False),
        sa.Column("next", sa.Text(), nullable=False),
        sa.Column("blockers", sa.Text(), nullable=True),
        sa.Column("confidence", sa.SmallInteger(), nullable=False),
        sa.Column("on_time", sa.Boolean(), nullable=False),
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
            "blockers IS NULL OR char_length(blockers) BETWEEN 1 AND 2000",
            name=op.f("ck_checkins_blockers_len"),
        ),
        sa.CheckConstraint(
            "char_length(done) BETWEEN 1 AND 2000", name=op.f("ck_checkins_done_len")
        ),
        sa.CheckConstraint(
            "char_length(next) BETWEEN 1 AND 2000", name=op.f("ck_checkins_next_len")
        ),
        sa.CheckConstraint("confidence BETWEEN 1 AND 5", name=op.f("ck_checkins_confidence_range")),
        sa.CheckConstraint(
            "extract(isodow FROM week_start) = 1", name=op.f("ck_checkins_week_starts_monday")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_checkins_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_member_id"],
            ["team_members.id"],
            name=op.f("fk_checkins_team_member_id_team_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checkins")),
        sa.UniqueConstraint("team_member_id", "week_start", name="uq_checkins_member_week"),
    )
    op.create_index(
        "ix_checkins_project_week",
        "checkins",
        ["project_id", sa.literal_column("week_start DESC"), "id"],
        unique=False,
    )
    op.add_column("files", sa.Column("project_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_files_project_created",
        "files",
        ["project_id", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text("project_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_foreign_key(
        op.f("fk_files_project_id_projects"), "files", "projects", ["project_id"], ["id"]
    )
    # ### end Alembic commands ###
    _security()
    _settings_v6()


def _security() -> None:
    """Helpers, the definer, triggers, file access and RLS policies (after the tables)."""
    op.create_check_constraint(
        op.f("ck_files_project_iff_kind"),
        "files",
        "(kind::text = 'PROJECT_FILE') = (project_id IS NOT NULL)",
    )
    op.execute(HELPERS)
    for fn in HELPER_NAMES:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, devsync_readonly")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {DML_ROLES}")
    op.execute(RECORD_ACTIVITY)
    op.execute(f"REVOKE ALL ON FUNCTION {RECORD_ACTIVITY_SIG} FROM PUBLIC, devsync_readonly")
    op.execute(f"GRANT EXECUTE ON FUNCTION {RECORD_ACTIVITY_SIG} TO {DML_ROLES}")
    op.execute(TRIGGERS)
    for fn in TRIGGER_FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, {DML_ROLES}, devsync_readonly")
    op.execute(FILE_ACCESS_0016)
    op.execute(_rls())
    op.execute(POLICIES)
    op.execute(FILE_POLICIES)
    # Append-only and trigger-written tables: no direct mutation by the runtime roles.
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE ON activity_events, checkins, task_evidence "
        f"FROM {DML_ROLES}"
    )
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON comment_revisions, discussion_post_revisions "
        f"FROM {DML_ROLES}"
    )
    op.execute(
        "REVOKE DELETE, TRUNCATE ON comments, discussion_posts, discussion_threads "
        f"FROM {DML_ROLES}"
    )


def _settings_v6() -> None:
    settings_table = sa.table(
        "platform_settings",
        sa.column("version", sa.Integer()),
        sa.column("values", postgresql.JSONB()),
        sa.column("reason", sa.Text()),
    )
    op.bulk_insert(
        settings_table,
        [{"version": 6, "values": json.loads(SETTINGS_V6.read_text(encoding="utf-8")),
          "reason": "Upload byte budget per day (spec §14.8, D147)"}],
    )  # fmt: skip


def downgrade() -> None:
    project_files = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM files WHERE kind::text = 'PROJECT_FILE'"))
        .scalar_one()
    )
    if project_files:
        raise RuntimeError(f"{project_files} project files exist; remove them before downgrading")
    op.execute("ALTER TABLE platform_settings DISABLE TRIGGER platform_settings_immutable")
    op.execute("DELETE FROM platform_settings WHERE version = 6")
    op.execute("ALTER TABLE platform_settings ENABLE TRIGGER platform_settings_immutable")
    op.execute(DROP_FILE_POLICIES)
    op.execute(FILE_ACCESS_0004)
    op.drop_constraint(op.f("ck_files_project_iff_kind"), "files", type_="check")
    # Policies and triggers go with their tables; the functions and enums after them.
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(op.f("fk_files_project_id_projects"), "files", type_="foreignkey")
    op.drop_index(
        "ix_files_project_created",
        table_name="files",
        postgresql_where=sa.text("project_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.drop_column("files", "project_id")
    op.drop_index("ix_checkins_project_week", table_name="checkins")
    op.drop_table("checkins")
    op.drop_index("ix_task_evidence_task", table_name="task_evidence")
    op.drop_table("task_evidence")
    op.drop_index("ix_task_dependencies_depends_on", table_name="task_dependencies")
    op.drop_table("task_dependencies")
    op.drop_index(
        op.f("ix_discussion_post_revisions_post_id"), table_name="discussion_post_revisions"
    )
    op.drop_table("discussion_post_revisions")
    op.drop_index("ix_tasks_project_assignee", table_name="tasks")
    op.drop_index("ix_tasks_milestone_status_position", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_discussion_posts_thread", table_name="discussion_posts")
    op.drop_table("discussion_posts")
    op.drop_index(op.f("ix_comment_revisions_comment_id"), table_name="comment_revisions")
    op.drop_table("comment_revisions")
    op.drop_index(
        "one_open_risk_per_entity", table_name="risks", postgresql_where=sa.text("status = 'OPEN'")
    )
    op.drop_index("ix_risks_project_status_severity", table_name="risks")
    op.drop_table("risks")
    op.drop_table("forecast_snapshots")
    op.drop_index("ix_discussion_threads_project", table_name="discussion_threads")
    op.drop_table("discussion_threads")
    op.drop_index("ix_comments_target", table_name="comments")
    op.drop_index("ix_comments_project", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_activity_events_project_subject", table_name="activity_events")
    op.drop_index("ix_activity_events_project_at", table_name="activity_events")
    op.drop_index("ix_activity_events_project_actor", table_name="activity_events")
    op.drop_table("activity_events")
    op.drop_table("notification_preferences")
    # ### end Alembic commands ###
    for fn in (*TRIGGER_FUNCTIONS, RECORD_ACTIVITY_SIG, *HELPER_NAMES):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    for enum_name in (
        "task_status",
        "task_difficulty",
        "evidence_kind",
        "comment_target",
        "risk_type",
        "risk_severity",
        "risk_status",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
    # Postgres can't drop an enum value: rebuild file_kind without PROJECT_FILE (none exist).
    op.execute("ALTER TYPE file_kind RENAME TO file_kind_0016")
    op.execute(
        "CREATE TYPE file_kind AS ENUM ('PORTFOLIO_IMAGE', 'CERTIFICATE', 'EXTERNAL_REVIEW')"
    )
    op.execute("ALTER TABLE files ALTER COLUMN kind TYPE file_kind USING kind::text::file_kind")
    op.execute("DROP TYPE file_kind_0016")
