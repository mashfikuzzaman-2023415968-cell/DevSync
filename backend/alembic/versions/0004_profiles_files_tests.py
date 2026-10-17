"""Profiles, files, portfolio, evidence and timed skill tests (Phase 3).

- Tables from spec §7.2 (+ `external_reviews` from §7.7 and the generic `files` table, §14.9).
- Row-level security on every new table (§14.15). `question_bank` is admin/SYSTEM only: web
  requests start attempts, read their questions, record answers and get scored through
  SECURITY DEFINER functions that never return the correct answer (§14.13 row 3).
- Public developer profiles and portfolio-image downloads go through definer functions that
  honour the profile's visibility; phone and email are never part of them.
- Seed: the 8 spec skills, one timed test per skill and the question bank (frozen JSON).

Revision ID: 0004_profiles_files_tests
Revises: 0003_public_stats
Create Date: 2026-10-17 17:54:10.192125+00:00
"""

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_profiles_files_tests"
down_revision: str | None = "0003_public_stats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEED = Path(__file__).resolve().parent.parent / "seed" / "skills_and_questions_v1.json"
DML_ROLES = "devsync_app, devsync_worker"

# Rows that belong to one user, keyed by this column.
OWNED = {
    "developer_profiles": "user_id",
    "client_profiles": "user_id",
    "developer_skills": "user_id",
    "files": "owner_id",
    "portfolio_items": "user_id",
    "certificates": "user_id",
    "external_reviews": "developer_id",
}
PROTECTED = (
    *OWNED,
    "portfolio_images",
    "question_bank",
    "test_attempts",
    "skill_evidence",
)

GUARDS = r"""
-- is_system() checks current_user, which inside a SECURITY DEFINER function is the function's
-- owner; definers use this instead (the login role of the worker connection, §14.15).
CREATE FUNCTION caller_is_system() RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public AS $$
  SELECT app_role() = 'SYSTEM' AND session_user = 'devsync_worker'
$$;

-- Who may see a developer's profile (and its portfolio images): PUBLIC → everyone;
-- CLIENTS_ONLY → signed-in clients, admins and the developer.
CREATE FUNCTION profile_visible(p_user uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT EXISTS (
    SELECT 1 FROM users u LEFT JOIN developer_profiles dp ON dp.user_id = u.id
    WHERE u.id = p_user AND u.role = 'DEVELOPER' AND u.status = 'ACTIVE'
      AND (coalesce(dp.visibility, 'PUBLIC') = 'PUBLIC'
           OR app_uid() = p_user
           OR (app_uid() IS NOT NULL AND app_role() IN ('CLIENT', 'ADMIN')))
  )
$$;
"""

DEFINER_FUNCTIONS = r"""
-- Start a timed attempt: 10 random active questions (seeded), server deadline. Only the
-- signed-in developer, one open attempt at a time, one scored attempt per test per 30 days.
CREATE FUNCTION start_test_attempt(p_test uuid, p_now timestamptz, p_seed bigint)
RETURNS TABLE (attempt_id uuid, deadline_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_user uuid := app_uid();
  v_test skill_tests%ROWTYPE;
  v_ids uuid[];
  v_last timestamptz;
BEGIN
  IF v_user IS NULL OR app_role() <> 'DEVELOPER' THEN
    RAISE EXCEPTION 'only developers take tests' USING ERRCODE = 'insufficient_privilege';
  END IF;
  -- One start at a time per developer and test (two parallel starts can't both pass the checks).
  PERFORM pg_advisory_xact_lock(hashtextextended(v_user::text || ':' || p_test::text, 0));
  SELECT * INTO v_test FROM skill_tests WHERE id = p_test AND active;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'test not found' USING ERRCODE = 'no_data_found';
  END IF;
  IF EXISTS (SELECT 1 FROM test_attempts a WHERE a.user_id = v_user AND a.test_id = p_test
             AND a.submitted_at IS NULL AND a.deadline_at > p_now) THEN
    RAISE EXCEPTION 'attempt already open' USING ERRCODE = 'unique_violation';
  END IF;
  SELECT max(a.started_at) INTO v_last FROM test_attempts a
  WHERE a.user_id = v_user AND a.test_id = p_test AND a.scored;
  IF v_last IS NOT NULL AND v_last > p_now - interval '30 days' THEN
    RAISE EXCEPTION 'retake not allowed before %', v_last + interval '30 days'
      USING ERRCODE = 'check_violation';
  END IF;
  PERFORM setseed(((p_seed % 2000000) - 1000000) / 1000000.0);
  -- Shuffle the active questions with the stored seed (stable base order → reproducible).
  SELECT array_agg(t.id) INTO v_ids FROM (
    SELECT b.id FROM (SELECT id FROM question_bank
                      WHERE skill_id = v_test.skill_id AND active ORDER BY id) b
    ORDER BY random() LIMIT v_test.question_count
  ) t;
  IF v_ids IS NULL OR cardinality(v_ids) < v_test.question_count THEN
    RAISE EXCEPTION 'question bank too small' USING ERRCODE = 'data_exception';
  END IF;
  RETURN QUERY
  INSERT INTO test_attempts (test_id, user_id, question_ids, answers, seed, started_at,
                             deadline_at, scored)
  VALUES (p_test, v_user, v_ids, '{}'::jsonb, p_seed, p_now,
          p_now + make_interval(secs => v_test.time_limit_seconds), true)
  RETURNING id, test_attempts.deadline_at;
END;
$$;

-- The questions of the caller's own attempt, in order, WITHOUT the correct answer.
CREATE FUNCTION attempt_questions(p_attempt uuid)
RETURNS TABLE (question_id uuid, ordinal int, text text, options jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT q.id, ord::int - 1, q.text, q.options
  FROM test_attempts a
  CROSS JOIN LATERAL unnest(a.question_ids) WITH ORDINALITY AS u(qid, ord)
  JOIN question_bank q ON q.id = u.qid
  WHERE a.id = p_attempt AND a.user_id = app_uid()
  ORDER BY ord
$$;

-- Record one answer before the deadline (the server clock decides).
CREATE FUNCTION record_test_answer(p_attempt uuid, p_question uuid, p_choice int, p_now timestamptz)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_attempt test_attempts%ROWTYPE;
BEGIN
  SELECT * INTO v_attempt FROM test_attempts WHERE id = p_attempt AND user_id = app_uid()
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'attempt not found' USING ERRCODE = 'no_data_found';
  END IF;
  IF v_attempt.submitted_at IS NOT NULL OR p_now > v_attempt.deadline_at THEN
    RETURN false;
  END IF;
  IF NOT (p_question = ANY (v_attempt.question_ids)) OR p_choice NOT BETWEEN 0 AND 3 THEN
    RAISE EXCEPTION 'invalid answer' USING ERRCODE = 'check_violation';
  END IF;
  UPDATE test_attempts SET answers = answers || jsonb_build_object(p_question::text, p_choice),
         updated_at = p_now
  WHERE id = p_attempt;
  RETURN true;
END;
$$;

-- Submit and score (the owner, or SYSTEM for expired attempts). Writes skill evidence once.
CREATE FUNCTION score_test_attempt(p_attempt uuid, p_now timestamptz)
RETURNS TABLE (score numeric, correct int, total int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_attempt test_attempts%ROWTYPE;
  v_correct int;
  v_total int;
  v_score numeric(4,3);
  v_skill uuid;
BEGIN
  SELECT * INTO v_attempt FROM test_attempts
  WHERE id = p_attempt AND (user_id = app_uid() OR caller_is_system()) FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'attempt not found' USING ERRCODE = 'no_data_found';
  END IF;
  IF v_attempt.submitted_at IS NOT NULL THEN
    RAISE EXCEPTION 'already submitted' USING ERRCODE = 'unique_violation';
  END IF;
  v_total := cardinality(v_attempt.question_ids);
  SELECT count(*) INTO v_correct FROM question_bank q
  WHERE q.id = ANY (v_attempt.question_ids)
    AND (v_attempt.answers ->> q.id::text)::int = q.correct_index;
  v_score := round(v_correct::numeric / greatest(v_total, 1), 3);
  UPDATE test_attempts SET submitted_at = p_now, score = v_score, updated_at = p_now
  WHERE id = p_attempt;
  IF v_attempt.scored THEN
    SELECT t.skill_id INTO v_skill FROM skill_tests t WHERE t.id = v_attempt.test_id;
    INSERT INTO skill_evidence (user_id, skill_id, source, score, attempt_id, at)
    VALUES (v_attempt.user_id, v_skill, 'TEST', v_score, p_attempt, p_now);
  END IF;
  RETURN QUERY SELECT v_score, v_correct, v_total;
END;
$$;

-- Public developer profile (no phone or email), honouring visibility; NULL when hidden.
-- A developer who never saved a profile is shown with the defaults.
CREATE FUNCTION public_developer_profile(p_user uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT CASE WHEN NOT profile_visible(p_user) THEN NULL ELSE jsonb_build_object(
    'id', u.id,
    'display_name', u.display_name,
    'member_since', u.created_at,
    'headline', coalesce(dp.headline, ''),
    'bio', coalesce(dp.bio, ''),
    'hours_per_week', coalesce(dp.hours_per_week, 20),
    'github_username', dp.github_username,
    'visibility', coalesce(dp.visibility, 'PUBLIC'),
    'skills', coalesce((
      SELECT jsonb_agg(jsonb_build_object('skill_id', s.id, 'name', s.name, 'domain', s.domain,
                                          'self_level', ds.self_level) ORDER BY s.name)
      FROM developer_skills ds JOIN skills s ON s.id = ds.skill_id WHERE ds.user_id = u.id), '[]'),
    'verified_scores', coalesce((
      SELECT jsonb_agg(jsonb_build_object('skill_id', e.skill_id, 'name', s.name, 'score', e.score::text,
                                          'at', e.at) ORDER BY s.name)
      FROM (SELECT DISTINCT ON (skill_id) skill_id, score, at FROM skill_evidence
            WHERE user_id = u.id ORDER BY skill_id, at DESC) e
      JOIN skills s ON s.id = e.skill_id), '[]'),
    'portfolio', coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'id', p.id, 'title', p.title, 'description', p.description, 'url', p.url,
        'skill_ids', p.skill_ids,
        'image_ids', coalesce((SELECT jsonb_agg(pi.file_id ORDER BY pi.position)
                               FROM portfolio_images pi WHERE pi.portfolio_item_id = p.id), '[]'))
        ORDER BY p.position)
      FROM portfolio_items p WHERE p.user_id = u.id), '[]'),
    'certificates', coalesce((
      SELECT jsonb_agg(jsonb_build_object('title', c.title, 'issuer', c.issuer) ORDER BY c.title)
      FROM certificates c WHERE c.user_id = u.id AND c.status = 'VERIFIED'), '[]')
  ) END
  FROM users u LEFT JOIN developer_profiles dp ON dp.user_id = u.id
  WHERE u.id = p_user
$$;

-- Where a file may be downloaded from, if the caller may see it: the owner, admins, or anyone
-- who can see the profile a portfolio image belongs to.
CREATE FUNCTION file_access(p_file uuid)
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
"""

TRIGGERS = r"""
-- Defence in depth behind the API's schemas: owners may edit their evidence, but only admins
-- (or SYSTEM) decide its verification, and a stored file's identity never changes.
CREATE FUNCTION guard_verification() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF is_admin() OR is_system() THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'PENDING' OR NEW.reviewed_by IS NOT NULL OR NEW.reviewed_at IS NOT NULL
       OR NEW.reason IS NOT NULL THEN
      RAISE EXCEPTION 'verification is decided by an admin' USING ERRCODE = 'insufficient_privilege';
    END IF;
  ELSIF (NEW.status, NEW.reviewed_by, NEW.reviewed_at, NEW.reason)
        IS DISTINCT FROM (OLD.status, OLD.reviewed_by, OLD.reviewed_at, OLD.reason) THEN
    RAISE EXCEPTION 'verification is decided by an admin' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER certificates_verification BEFORE INSERT OR UPDATE ON certificates
  FOR EACH ROW EXECUTE FUNCTION guard_verification();
CREATE TRIGGER external_reviews_verification BEFORE INSERT OR UPDATE ON external_reviews
  FOR EACH ROW EXECUTE FUNCTION guard_verification();

CREATE FUNCTION files_identity_immutable() RETURNS trigger
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
CREATE TRIGGER files_identity BEFORE UPDATE ON files
  FOR EACH ROW EXECUTE FUNCTION files_identity_immutable();
"""

HELPER_NAMES = ("profile_visible(uuid)", "caller_is_system()")
TRIGGER_FUNCTIONS = ("guard_verification()", "files_identity_immutable()")
DEFINER_NAMES = (
    "profile_visible(uuid)",
    "start_test_attempt(uuid, timestamptz, bigint)",
    "attempt_questions(uuid)",
    "record_test_answer(uuid, uuid, int, timestamptz)",
    "score_test_attempt(uuid, timestamptz)",
    "public_developer_profile(uuid)",
    "file_access(uuid)",
)


def _policies() -> str:
    stmts: list[str] = []
    for table in PROTECTED:
        stmts.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        stmts.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        stmts.append(
            f"CREATE POLICY migrator_all ON {table} TO devsync_migrator USING (true) WITH CHECK (true)"
        )
    for table, col in OWNED.items():
        stmts += [
            f"CREATE POLICY owner_select ON {table} FOR SELECT TO {DML_ROLES} "
            f"USING ({col} = app_uid() OR is_admin() OR is_system())",
            f"CREATE POLICY owner_insert ON {table} FOR INSERT TO {DML_ROLES} "
            f"WITH CHECK ({col} = app_uid() OR is_system())",
            f"CREATE POLICY owner_update ON {table} FOR UPDATE TO {DML_ROLES} "
            f"USING ({col} = app_uid() OR is_system()) WITH CHECK ({col} = app_uid() OR is_system())",
            f"CREATE POLICY owner_delete ON {table} FOR DELETE TO {DML_ROLES} "
            f"USING ({col} = app_uid() OR is_system())",
        ]
    stmts += [
        # Admins verify certificates and external reviews (console in Phase 12).
        "CREATE POLICY admin_verify ON certificates FOR UPDATE TO devsync_app "
        "USING (is_admin()) WITH CHECK (is_admin())",
        "CREATE POLICY admin_verify ON external_reviews FOR UPDATE TO devsync_app "
        "USING (is_admin()) WITH CHECK (is_admin())",
        # Portfolio images follow their item's owner.
        f"CREATE POLICY item_owner ON portfolio_images FOR ALL TO {DML_ROLES} "  # noqa: S608 - DDL from constants
        "USING (EXISTS (SELECT 1 FROM portfolio_items p WHERE p.id = portfolio_item_id "
        "AND (p.user_id = app_uid() OR is_system()))) "
        "WITH CHECK (EXISTS (SELECT 1 FROM portfolio_items p WHERE p.id = portfolio_item_id "
        "AND (p.user_id = app_uid() OR is_system())))",
        "CREATE POLICY admin_select ON portfolio_images FOR SELECT TO devsync_app USING (is_admin())",
        # The question bank holds the answers: admins and SYSTEM only.
        f"CREATE POLICY admin_system ON question_bank FOR ALL TO {DML_ROLES} "
        "USING (is_admin() OR is_system()) WITH CHECK (is_admin() OR is_system())",
        # Attempts and evidence are read by their owner and admins; written only through the
        # definer functions above (no INSERT/UPDATE policy for web requests).
        f"CREATE POLICY owner_select ON test_attempts FOR SELECT TO {DML_ROLES} "
        "USING (user_id = app_uid() OR is_admin() OR is_system())",
        f"CREATE POLICY owner_select ON skill_evidence FOR SELECT TO {DML_ROLES} "
        "USING (user_id = app_uid() OR is_admin() OR is_system())",
    ]
    return ";\n".join(stmts) + ";"


def _seed() -> None:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    tests = sa.table(
        "skill_tests", sa.column("skill_id", postgresql.UUID()), sa.column("title", sa.Text()),
        sa.column("question_count", sa.SmallInteger()),
        sa.column("time_limit_seconds", sa.Integer()),
    )  # fmt: skip
    questions = sa.table(
        "question_bank", sa.column("skill_id", postgresql.UUID()), sa.column("text", sa.Text()),
        sa.column("options", postgresql.JSONB()), sa.column("correct_index", sa.SmallInteger()),
        sa.column("difficulty", sa.SmallInteger()),
    )  # fmt: skip
    conn = op.get_bind()
    for skill in data["skills"]:
        skill_id = conn.execute(
            sa.text(
                "INSERT INTO skills (name, domain) VALUES (:n, CAST(:d AS skill_domain)) RETURNING id"
            ),
            {"n": skill["name"], "d": skill["domain"]},
        ).scalar_one()
        op.bulk_insert(
            tests,
            [{"skill_id": skill_id, "title": f"{skill['name']} skill test",
              "question_count": 10, "time_limit_seconds": 600}],
        )  # fmt: skip
        op.bulk_insert(
            questions,
            [
                {"skill_id": skill_id, "text": q["text"], "options": q["options"],
                 "correct_index": q["answer"], "difficulty": q.get("difficulty", 2)}
                for q in skill["questions"]
            ],
        )  # fmt: skip


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "skills",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "domain",
            sa.Enum(
                "FRONTEND",
                "BACKEND",
                "DATABASE",
                "MOBILE",
                "DESIGN",
                "TESTING",
                "DEVOPS",
                "DATA",
                name="skill_domain",
            ),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 60", name=op.f("ck_skills_name_len")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
        sa.UniqueConstraint("name", name=op.f("uq_skills_name")),
    )
    op.create_table(
        "client_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization", sa.Text(), server_default="", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
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
            "website IS NULL OR (website ~ '^https://' AND char_length(website) <= 300)",
            name=op.f("ck_client_profiles_website_https"),
        ),
        sa.CheckConstraint(
            "char_length(description) <= 2000", name=op.f("ck_client_profiles_description_len")
        ),
        sa.CheckConstraint(
            "char_length(organization) <= 120", name=op.f("ck_client_profiles_organization_len")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_client_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_client_profiles_user_id")),
    )
    op.create_table(
        "developer_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("headline", sa.Text(), server_default="", nullable=False),
        sa.Column("bio", sa.Text(), server_default="", nullable=False),
        sa.Column("hours_per_week", sa.SmallInteger(), server_default="20", nullable=False),
        sa.Column("github_username", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), server_default="Asia/Dhaka", nullable=False),
        sa.Column(
            "visibility",
            sa.Enum("PUBLIC", "CLIENTS_ONLY", name="profile_visibility"),
            server_default="PUBLIC",
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
            "github_username IS NULL OR github_username ~ '^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$'",
            name=op.f("ck_developer_profiles_github_username_format"),
        ),
        sa.CheckConstraint("char_length(bio) <= 2000", name=op.f("ck_developer_profiles_bio_len")),
        sa.CheckConstraint(
            "char_length(headline) <= 120", name=op.f("ck_developer_profiles_headline_len")
        ),
        sa.CheckConstraint(
            "hours_per_week BETWEEN 1 AND 80", name=op.f("ck_developer_profiles_hours_range")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_developer_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_developer_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_developer_profiles_user_id")),
    )
    op.create_table(
        "developer_skills",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("self_level", sa.SmallInteger(), nullable=False),
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
            "self_level BETWEEN 1 AND 5", name=op.f("ck_developer_skills_level_range")
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_developer_skills_skill_id_skills")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_developer_skills_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_developer_skills")),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_developer_skills_user_skill"),
    )
    op.create_index(
        op.f("ix_developer_skills_skill_id"), "developer_skills", ["skill_id"], unique=False
    )
    op.create_index(
        op.f("ix_developer_skills_user_id"), "developer_skills", ["user_id"], unique=False
    )
    op.create_table(
        "files",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("PORTFOLIO_IMAGE", "CERTIFICATE", "EXTERNAL_REVIEW", name="file_kind"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.UUID(), nullable=False),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column(
            "scan_status",
            sa.Enum("SKIPPED", "CLEAN", "INFECTED", name="scan_status"),
            server_default="SKIPPED",
            nullable=False,
        ),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            "char_length(original_name) BETWEEN 1 AND 200", name=op.f("ck_files_name_len")
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_files_size_positive")),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_files_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_files_storage_key")),
    )
    op.create_index(op.f("ix_files_owner_id"), "files", ["owner_id"], unique=False)
    op.create_table(
        "portfolio_items",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("skill_ids", postgresql.ARRAY(sa.UUID()), server_default="{}", nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
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
            "url IS NULL OR (url ~ '^https://' AND char_length(url) <= 300)",
            name=op.f("ck_portfolio_items_url_https"),
        ),
        sa.CheckConstraint(
            "cardinality(skill_ids) <= 8", name=op.f("ck_portfolio_items_skills_max")
        ),
        sa.CheckConstraint(
            "char_length(description) <= 2000", name=op.f("ck_portfolio_items_description_len")
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 120", name=op.f("ck_portfolio_items_title_len")
        ),
        sa.CheckConstraint(
            "position BETWEEN 0 AND 19", name=op.f("ck_portfolio_items_position_range")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_portfolio_items_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_items")),
    )
    op.create_index(
        op.f("ix_portfolio_items_user_id"), "portfolio_items", ["user_id"], unique=False
    )
    op.create_table(
        "question_bank",
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correct_index", sa.SmallInteger(), nullable=False),
        sa.Column("difficulty", sa.SmallInteger(), server_default="2", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
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
            "jsonb_typeof(options) = 'array' AND jsonb_array_length(options) = 4",
            name=op.f("ck_question_bank_four_options"),
        ),
        sa.CheckConstraint(
            "char_length(text) BETWEEN 5 AND 1000", name=op.f("ck_question_bank_text_len")
        ),
        sa.CheckConstraint(
            "correct_index BETWEEN 0 AND 3", name=op.f("ck_question_bank_correct_range")
        ),
        sa.CheckConstraint(
            "difficulty BETWEEN 1 AND 3", name=op.f("ck_question_bank_difficulty_range")
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_question_bank_skill_id_skills")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_bank")),
    )
    op.create_index(op.f("ix_question_bank_skill_id"), "question_bank", ["skill_id"], unique=False)
    op.create_table(
        "skill_tests",
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("question_count", sa.SmallInteger(), server_default="10", nullable=False),
        sa.Column("time_limit_seconds", sa.Integer(), server_default="600", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
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
            "question_count BETWEEN 1 AND 50", name=op.f("ck_skill_tests_count_range")
        ),
        sa.CheckConstraint(
            "time_limit_seconds BETWEEN 60 AND 7200", name=op.f("ck_skill_tests_time_range")
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_skill_tests_skill_id_skills")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_tests")),
    )
    op.create_index(op.f("ix_skill_tests_skill_id"), "skill_tests", ["skill_id"], unique=False)
    op.create_table(
        "certificates",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "VERIFIED", "REJECTED", name="verification_status"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
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
            "char_length(issuer) BETWEEN 1 AND 120", name=op.f("ck_certificates_issuer_len")
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 120", name=op.f("ck_certificates_title_len")
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name=op.f("fk_certificates_file_id_files")
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name=op.f("fk_certificates_reviewed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_certificates_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_certificates")),
        sa.UniqueConstraint("file_id", name=op.f("uq_certificates_file_id")),
    )
    op.create_index(op.f("ix_certificates_user_id"), "certificates", ["user_id"], unique=False)
    op.create_table(
        "external_reviews",
        sa.Column("developer_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("rating_norm", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("project_date", sa.Date(), nullable=False),
        sa.Column("evidence_file_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "VERIFIED", "REJECTED", name="verification_status"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
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
            "char_length(source) BETWEEN 1 AND 80", name=op.f("ck_external_reviews_source_len")
        ),
        sa.CheckConstraint(
            "rating_norm BETWEEN 0 AND 1", name=op.f("ck_external_reviews_rating_range")
        ),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["users.id"],
            name=op.f("fk_external_reviews_developer_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_file_id"],
            ["files.id"],
            name=op.f("fk_external_reviews_evidence_file_id_files"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name=op.f("fk_external_reviews_reviewed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_reviews")),
        sa.UniqueConstraint("evidence_file_id", name=op.f("uq_external_reviews_evidence_file_id")),
    )
    op.create_index(
        op.f("ix_external_reviews_developer_id"), "external_reviews", ["developer_id"], unique=False
    )
    op.create_table(
        "portfolio_images",
        sa.Column("portfolio_item_id", sa.UUID(), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
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
            "position BETWEEN 0 AND 4", name=op.f("ck_portfolio_images_position_range")
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name=op.f("fk_portfolio_images_file_id_files")
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_item_id"],
            ["portfolio_items.id"],
            name=op.f("fk_portfolio_images_portfolio_item_id_portfolio_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_images")),
        sa.UniqueConstraint("file_id", name=op.f("uq_portfolio_images_file_id")),
    )
    op.create_index(
        op.f("ix_portfolio_images_portfolio_item_id"),
        "portfolio_images",
        ["portfolio_item_id"],
        unique=False,
    )
    op.create_table(
        "test_attempts",
        sa.Column("test_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("question_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column(
            "answers", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("scored", sa.Boolean(), server_default="true", nullable=False),
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
            "deadline_at > started_at", name=op.f("ck_test_attempts_deadline_after_start")
        ),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 1", name=op.f("ck_test_attempts_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["test_id"], ["skill_tests.id"], name=op.f("fk_test_attempts_test_id_skill_tests")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_test_attempts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_attempts")),
    )
    op.create_index(
        "ix_test_attempts_user_test_started",
        "test_attempts",
        ["user_id", "test_id", "started_at"],
        unique=False,
    )
    op.create_table(
        "skill_evidence",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("TEST", "CODING", "ADMIN_PORTFOLIO", name="evidence_source"),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("attempt_id", sa.UUID(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint("score BETWEEN 0 AND 1", name=op.f("ck_skill_evidence_score_range")),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["test_attempts.id"],
            name=op.f("fk_skill_evidence_attempt_id_test_attempts"),
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_skill_evidence_skill_id_skills")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_skill_evidence_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_evidence")),
        sa.UniqueConstraint("attempt_id", name=op.f("uq_skill_evidence_attempt_id")),
    )
    op.create_index(
        "ix_skill_evidence_user_skill", "skill_evidence", ["user_id", "skill_id"], unique=False
    )
    # ### end Alembic commands ###

    op.execute(GUARDS)
    op.execute(DEFINER_FUNCTIONS)
    op.execute(TRIGGERS)
    for fn in DEFINER_NAMES:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, devsync_readonly")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {DML_ROLES}")
    op.execute(_policies())
    # The taxonomy is public and RLS-exempt (rls_exempt.yml): read-only for the runtime roles.
    op.execute(f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON skills, skill_tests FROM {DML_ROLES}")
    _seed()


def downgrade() -> None:
    for fn in DEFINER_NAMES:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    for fn in HELPER_NAMES:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_skill_evidence_user_skill", table_name="skill_evidence")
    op.drop_table("skill_evidence")
    op.drop_index("ix_test_attempts_user_test_started", table_name="test_attempts")
    op.drop_table("test_attempts")
    op.drop_index(op.f("ix_portfolio_images_portfolio_item_id"), table_name="portfolio_images")
    op.drop_table("portfolio_images")
    op.drop_index(op.f("ix_external_reviews_developer_id"), table_name="external_reviews")
    op.drop_table("external_reviews")
    op.drop_index(op.f("ix_certificates_user_id"), table_name="certificates")
    op.drop_table("certificates")
    op.drop_index(op.f("ix_skill_tests_skill_id"), table_name="skill_tests")
    op.drop_table("skill_tests")
    op.drop_index(op.f("ix_question_bank_skill_id"), table_name="question_bank")
    op.drop_table("question_bank")
    op.drop_index(op.f("ix_portfolio_items_user_id"), table_name="portfolio_items")
    op.drop_table("portfolio_items")
    op.drop_index(op.f("ix_files_owner_id"), table_name="files")
    op.drop_table("files")
    op.drop_index(op.f("ix_developer_skills_user_id"), table_name="developer_skills")
    op.drop_index(op.f("ix_developer_skills_skill_id"), table_name="developer_skills")
    op.drop_table("developer_skills")
    op.drop_table("developer_profiles")
    op.drop_table("client_profiles")
    op.drop_table("skills")
    # ### end Alembic commands ###
    for fn in TRIGGER_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    for enum_name in (
        "evidence_source",
        "verification_status",
        "scan_status",
        "file_kind",
        "profile_visibility",
        "skill_domain",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
