"""Identity tables, row-level security foundation, pre-auth functions, settings v2.

Revision ID: 0002_identity_rls
Revises: 0001_foundation
Create Date: 2026-10-17

Row-level security (spec §14.15) is the second gate after application
authorization: every table has ENABLE + FORCE ROW LEVEL SECURITY and policies
keyed on the transaction-local request context (`app.user_id`, `app.role`) that
the app sets per transaction. Missing context matches nothing (fail closed).

- `is_system()` is true only for the `devsync_worker` role with `app.role=SYSTEM`,
  so web requests (role `devsync_app`) can never act as SYSTEM.
- Pre-authentication operations (login lookup, failure counting, session restore,
  consuming email tokens, registration) run through narrow SECURITY DEFINER
  functions owned by `devsync_migrator`; a `TO devsync_migrator` policy lets them
  (and migrations) see rows, while they return only the columns each flow needs.
- The audit hash-chain trigger becomes SECURITY DEFINER so the chain is computed
  over all rows even when the inserting user cannot read the log.
"""

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_identity_rls"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_V2 = Path(__file__).resolve().parent.parent / "seed" / "platform_settings_v2.json"
DML_ROLES = "devsync_app, devsync_worker"

# Tables whose rows belong to exactly one user (`user_id`): own rows + SYSTEM.
OWN_ROW_TABLES = (
    "sessions",
    "otp_codes",
    "email_tokens",
    "totp_credentials",
    "recovery_codes",
    "devices_seen",
    "idempotency_keys",
)
ALL_TABLES = (
    "users",
    *OWN_ROW_TABLES,
    "notifications",
    "email_outbox",
    "audit_log",
    "platform_settings",
    "jobs",
)

HELPERS = r"""
CREATE FUNCTION app_uid() RETURNS uuid
LANGUAGE sql STABLE SET search_path = pg_catalog, public AS $$
  SELECT nullif(current_setting('app.user_id', true), '')::uuid
$$;

CREATE FUNCTION app_role() RETURNS text
LANGUAGE sql STABLE SET search_path = pg_catalog, public AS $$
  SELECT coalesce(nullif(current_setting('app.role', true), ''), 'GUEST')
$$;

CREATE FUNCTION is_admin() RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public AS $$
  SELECT app_role() = 'ADMIN' AND app_uid() IS NOT NULL
$$;

-- SYSTEM context is only honoured for the worker's database role (§14.15).
CREATE FUNCTION is_system() RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public AS $$
  SELECT app_role() = 'SYSTEM' AND current_user = 'devsync_worker'
$$;
"""

DEFINER_FUNCTIONS = r"""
CREATE FUNCTION auth_create_user(
  p_email text, p_phone text, p_password_hash text, p_role user_role, p_display_name text
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_id uuid;
BEGIN
  IF p_role NOT IN ('CLIENT', 'DEVELOPER') THEN
    RAISE EXCEPTION 'self-registration cannot create role %', p_role
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO users (email, phone_e164, password_hash, role, status, display_name)
  VALUES (p_email, p_phone, p_password_hash, p_role, 'PENDING', p_display_name)
  RETURNING id INTO v_id;
  RETURN v_id;
EXCEPTION WHEN unique_violation THEN
  RETURN NULL;  -- duplicate email or phone: caller answers uniformly
END;
$$;

CREATE FUNCTION auth_login_lookup(p_email text)
RETURNS TABLE (
  id uuid, password_hash text, role user_role, status user_status,
  failed_login_count smallint, first_failed_login_at timestamptz, locked_until timestamptz
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT u.id, u.password_hash, u.role, u.status, u.failed_login_count,
         u.first_failed_login_at, u.locked_until
  FROM users u WHERE u.email = p_email::citext AND u.status <> 'DELETED'
$$;

CREATE FUNCTION auth_record_login_failure(
  p_user uuid, p_now timestamptz, p_window_seconds int, p_lock_after int, p_lock_minutes int
) RETURNS TABLE (failed_login_count smallint, locked_until timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  RETURN QUERY
  UPDATE users u SET
    failed_login_count = CASE
      WHEN u.first_failed_login_at IS NULL
        OR u.first_failed_login_at < p_now - make_interval(secs => p_window_seconds)
      THEN 1 ELSE least(u.failed_login_count + 1, 32000) END,
    first_failed_login_at = CASE
      WHEN u.first_failed_login_at IS NULL
        OR u.first_failed_login_at < p_now - make_interval(secs => p_window_seconds)
      THEN p_now ELSE u.first_failed_login_at END,
    locked_until = CASE
      WHEN (CASE WHEN u.first_failed_login_at IS NULL
                   OR u.first_failed_login_at < p_now - make_interval(secs => p_window_seconds)
                 THEN 1 ELSE u.failed_login_count + 1 END) >= p_lock_after
      THEN p_now + make_interval(mins => p_lock_minutes) ELSE u.locked_until END,
    updated_at = p_now
  WHERE u.id = p_user
  RETURNING u.failed_login_count, u.locked_until;
END;
$$;

CREATE FUNCTION auth_session_restore(p_token_hash bytea)
RETURNS TABLE (
  session_id uuid, user_id uuid, csrf_secret bytea, created_at timestamptz,
  last_seen_at timestamptz, rotated_at timestamptz, expires_at timestamptz,
  step_up_until timestamptz, totp_verified boolean, role user_role, status user_status
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT s.id, s.user_id, s.csrf_secret, s.created_at, s.last_seen_at, s.rotated_at,
         s.expires_at, s.step_up_until, s.totp_verified, u.role, u.status
  FROM sessions s JOIN users u ON u.id = s.user_id
  WHERE s.token_hash = p_token_hash AND s.revoked_at IS NULL
$$;

CREATE FUNCTION auth_consume_email_token(
  p_token_hash bytea, p_purpose email_token_purpose, p_now timestamptz
) RETURNS uuid
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  UPDATE email_tokens SET consumed_at = p_now
  WHERE token_hash = p_token_hash AND purpose = p_purpose
    AND consumed_at IS NULL AND expires_at > p_now
  RETURNING user_id
$$;

CREATE FUNCTION auth_user_by_email(p_email text)
RETURNS TABLE (id uuid, status user_status, display_name text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT u.id, u.status, u.display_name FROM users u
  WHERE u.email = p_email::citext AND u.status <> 'DELETED'
$$;

-- Platform settings are needed in every request (rate limits) but the table is admin-only.
CREATE FUNCTION active_settings() RETURNS TABLE (version int, "values" jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT ps.version, ps.values FROM platform_settings ps ORDER BY ps.version DESC LIMIT 1
$$;

ALTER FUNCTION audit_log_chain() SECURITY DEFINER;
ALTER FUNCTION audit_verify_chain() SECURITY DEFINER;
"""

DEFINER_NAMES = (
    "auth_create_user(text, text, text, user_role, text)",
    "auth_login_lookup(text)",
    "auth_record_login_failure(uuid, timestamptz, int, int, int)",
    "auth_session_restore(bytea)",
    "auth_consume_email_token(bytea, email_token_purpose, timestamptz)",
    "auth_user_by_email(text)",
    "active_settings()",
)


def _policies() -> str:
    """Policy DDL for every table (built in Python to keep the per-table rules readable)."""
    stmts: list[str] = []
    for table in ALL_TABLES:
        stmts.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        stmts.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        stmts.append(
            f"CREATE POLICY migrator_all ON {table} TO devsync_migrator USING (true) WITH CHECK (true)"
        )
    for table in OWN_ROW_TABLES:
        stmts.append(
            f"CREATE POLICY own_rows ON {table} TO {DML_ROLES} "
            "USING (user_id = app_uid() OR is_system()) "
            "WITH CHECK (user_id = app_uid() OR is_system())"
        )
    stmts += [
        # users: read/update own row; admins read and update (suspend etc.); SYSTEM all.
        "CREATE POLICY users_select ON users FOR SELECT TO devsync_app, devsync_worker "
        "USING (id = app_uid() OR is_admin() OR is_system())",
        "CREATE POLICY users_update ON users FOR UPDATE TO devsync_app, devsync_worker "
        "USING (id = app_uid() OR is_admin() OR is_system()) "
        "WITH CHECK (id = app_uid() OR is_admin() OR is_system())",
        "CREATE POLICY users_insert ON users FOR INSERT TO devsync_worker WITH CHECK (is_system())",
        # notifications: owners read and mark read; SYSTEM creates.
        "CREATE POLICY notif_select ON notifications FOR SELECT TO devsync_app, devsync_worker "
        "USING (user_id = app_uid() OR is_system())",
        "CREATE POLICY notif_update ON notifications FOR UPDATE TO devsync_app, devsync_worker "
        "USING (user_id = app_uid() OR is_system()) WITH CHECK (user_id = app_uid() OR is_system())",
        "CREATE POLICY notif_insert ON notifications FOR INSERT TO devsync_worker WITH CHECK (is_system())",
        # email outbox: any request may enqueue a PENDING email; only SYSTEM reads/sends.
        "CREATE POLICY outbox_insert ON email_outbox FOR INSERT TO devsync_app, devsync_worker "
        "WITH CHECK (status = 'PENDING')",
        "CREATE POLICY outbox_system ON email_outbox FOR ALL TO devsync_worker "
        "USING (is_system()) WITH CHECK (is_system())",
        # audit log: anyone may append (the trigger computes the chain); admins and SYSTEM read.
        "CREATE POLICY audit_insert ON audit_log FOR INSERT TO devsync_app, devsync_worker WITH CHECK (true)",
        "CREATE POLICY audit_select ON audit_log FOR SELECT TO devsync_app, devsync_worker "
        "USING (is_admin() OR is_system())",
        # platform settings: admins read and add versions (step-up enforced in the app); SYSTEM reads.
        "CREATE POLICY settings_select ON platform_settings FOR SELECT TO devsync_app, devsync_worker "
        "USING (is_admin() OR is_system())",
        "CREATE POLICY settings_insert ON platform_settings FOR INSERT TO devsync_app, devsync_worker "
        "WITH CHECK (is_admin() OR is_system())",
        # jobs: requester and admins read; SYSTEM manages.
        "CREATE POLICY jobs_select ON jobs FOR SELECT TO devsync_app, devsync_worker "
        "USING (requested_by = app_uid() OR is_admin() OR is_system())",
        "CREATE POLICY jobs_insert ON jobs FOR INSERT TO devsync_app, devsync_worker "
        "WITH CHECK (requested_by = app_uid() OR is_system())",
        "CREATE POLICY jobs_update ON jobs FOR UPDATE TO devsync_worker "
        "USING (is_system()) WITH CHECK (is_system())",
    ]
    return ";\n".join(stmts) + ";"


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "email_outbox",
        sa.Column("to_email", sa.Text(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SENT", "FAILED", name="outbox_status"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
    )
    op.create_index(
        "ix_email_outbox_due", "email_outbox", ["status", "next_attempt_at"], unique=False
    )
    op.create_table(
        "users",
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("phone_e164", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column(
            "role", sa.Enum("CLIENT", "DEVELOPER", "ADMIN", name="user_role"), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ACTIVE", "SUSPENDED", "DELETED", name="user_status"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("first_failed_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
            "char_length(display_name) BETWEEN 1 AND 80", name=op.f("ck_users_display_name_length")
        ),
        sa.CheckConstraint(
            "failed_login_count >= 0", name=op.f("ck_users_failed_login_count_nonneg")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("phone_e164", name=op.f("uq_users_phone_e164")),
    )
    op.create_table(
        "devices_seen",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("fingerprint_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_devices_seen_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices_seen")),
        sa.UniqueConstraint("user_id", "fingerprint_hash", name="uq_devices_seen_user_fp"),
    )
    op.create_table(
        "email_tokens",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "purpose", sa.Enum("VERIFY", "RESET", name="email_token_purpose"), nullable=False
        ),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_tokens_token_hash")),
    )
    op.create_index(op.f("ix_email_tokens_user_id"), "email_tokens", ["user_id"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link_path", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_user_read_created",
        "notifications",
        ["user_id", "read_at", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "otp_codes",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "purpose", sa.Enum("PHONE_VERIFY", "LOGIN_STEP_UP", name="otp_purpose"), nullable=False
        ),
        sa.Column("code_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_otp_codes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_otp_codes")),
    )
    op.create_index(op.f("ix_otp_codes_user_id"), "otp_codes", ["user_id"], unique=False)
    op.create_table(
        "recovery_codes",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recovery_codes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recovery_codes")),
    )
    op.create_index(op.f("ix_recovery_codes_user_id"), "recovery_codes", ["user_id"], unique=False)
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("csrf_secret", sa.LargeBinary(), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "rotated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("step_up_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("totp_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index("ix_sessions_user_revoked", "sessions", ["user_id", "revoked_at"], unique=False)
    op.create_table(
        "totp_credentials",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("secret_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_totp_credentials_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_totp_credentials")),
        sa.UniqueConstraint("user_id", name=op.f("uq_totp_credentials_user_id")),
    )
    op.create_foreign_key(
        op.f("fk_audit_log_actor_id_users"),
        "audit_log",
        "users",
        ["actor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_idempotency_keys_user_id_users"),
        "idempotency_keys",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_jobs_requested_by_users"),
        "jobs",
        "users",
        ["requested_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # ### end Alembic commands ###

    op.execute(HELPERS)
    op.execute(DEFINER_FUNCTIONS)
    for fn in DEFINER_NAMES:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, devsync_readonly")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {DML_ROLES}")
    op.execute(_policies())

    document = json.loads(SEED_V2.read_text(encoding="utf-8"))
    settings_table = sa.table(
        "platform_settings",
        sa.column("version", sa.Integer()),
        sa.column("values", postgresql.JSONB()),
        sa.column("reason", sa.Text()),
    )
    op.bulk_insert(
        settings_table,
        [{"version": 2, "values": document, "reason": "Rate limits from spec section 14.8"}],
    )


def downgrade() -> None:
    op.execute("ALTER TABLE platform_settings DISABLE TRIGGER platform_settings_immutable")
    op.execute("DELETE FROM platform_settings WHERE version = 2")
    op.execute("ALTER TABLE platform_settings ENABLE TRIGGER platform_settings_immutable")
    for table in ALL_TABLES:
        op.execute(f"DROP POLICY IF EXISTS migrator_all ON {table}")
        for name in (
            "own_rows",
            "users_select",
            "users_update",
            "users_insert",
            "notif_select",
            "notif_update",
            "notif_insert",
            "outbox_insert",
            "outbox_system",
            "audit_insert",
            "audit_select",
            "settings_select",
            "settings_insert",
            "jobs_select",
            "jobs_insert",
            "jobs_update",
        ):
            op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER FUNCTION audit_log_chain() SECURITY INVOKER")
    op.execute("ALTER FUNCTION audit_verify_chain() SECURITY INVOKER")
    for fn in DEFINER_NAMES:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    for fn in ("is_system()", "is_admin()", "app_role()", "app_uid()"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    op.drop_constraint(op.f("fk_jobs_requested_by_users"), "jobs", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_idempotency_keys_user_id_users"), "idempotency_keys", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_audit_log_actor_id_users"), "audit_log", type_="foreignkey")
    op.drop_table("totp_credentials")
    op.drop_index("ix_sessions_user_revoked", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_recovery_codes_user_id"), table_name="recovery_codes")
    op.drop_table("recovery_codes")
    op.drop_index(op.f("ix_otp_codes_user_id"), table_name="otp_codes")
    op.drop_table("otp_codes")
    op.drop_index("ix_notifications_user_read_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_email_tokens_user_id"), table_name="email_tokens")
    op.drop_table("email_tokens")
    op.drop_table("devices_seen")
    op.drop_table("users")
    op.drop_index("ix_email_outbox_due", table_name="email_outbox")
    op.drop_table("email_outbox")
    for enum_name in (
        "outbox_status",
        "email_token_purpose",
        "otp_purpose",
        "user_status",
        "user_role",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
    # ### end Alembic commands ###
