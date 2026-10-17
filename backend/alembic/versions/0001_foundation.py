"""Foundation: platform settings, append-only hash-chained audit log, jobs, idempotency keys.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-10-17

Security notes (spec §7, §14.11):
- `audit_log` is append-only: a BEFORE UPDATE/DELETE row trigger and a BEFORE
  TRUNCATE statement trigger raise, and the app/worker roles have no
  UPDATE/DELETE grants on it.
- The hash chain is computed in the database (`audit_log_chain` trigger) under
  a transaction-level advisory lock so concurrent inserts cannot fork the chain.
- `platform_settings` rows are immutable versions: app/worker may only INSERT/SELECT.
- The v1 settings document is a frozen snapshot (seed/platform_settings_v1.json);
  a unit test asserts it equals the schema defaults and validates.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "platform_settings_v1.json"
DML_ROLES = "devsync_app, devsync_worker"

AUDIT_FUNCTIONS = r"""
CREATE FUNCTION audit_row_hash(prev bytea, r audit_log) RETURNS bytea
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, public AS $$
  SELECT sha256(
    coalesce(prev, '\x'::bytea) ||
    convert_to(
      jsonb_build_object(
        'seq', r.seq,
        'id', r.id,
        'actor_id', r.actor_id,
        'actor_role', r.actor_role,
        'action', r.action,
        'entity_type', r.entity_type,
        'entity_id', r.entity_id,
        'before', r.before,
        'after', r.after,
        'ip', r.ip::text,
        'request_id', r.request_id,
        'at', to_char(r.at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
      )::text,
      'UTF8'
    )
  )
$$;

CREATE FUNCTION audit_log_chain() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE
  last_hash bytea;
BEGIN
  -- Serialize chain extension so two concurrent inserts can't share a prev_hash.
  PERFORM pg_advisory_xact_lock(hashtext('devsync.audit_log.chain'));
  NEW.at := coalesce(NEW.at, now());
  SELECT hash INTO last_hash FROM audit_log ORDER BY seq DESC LIMIT 1;
  NEW.prev_hash := last_hash;
  NEW.hash := audit_row_hash(last_hash, NEW);
  RETURN NEW;
END;
$$;

CREATE FUNCTION reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE FUNCTION audit_verify_chain() RETURNS bigint
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public AS $$
DECLARE
  r audit_log;
  expected_prev bytea := NULL;
BEGIN
  FOR r IN SELECT * FROM audit_log ORDER BY seq LOOP
    IF r.prev_hash IS DISTINCT FROM expected_prev
       OR r.hash IS DISTINCT FROM audit_row_hash(expected_prev, r) THEN
      RETURN r.seq;
    END IF;
    expected_prev := r.hash;
  END LOOP;
  RETURN NULL;
END;
$$;

CREATE TRIGGER audit_log_chain BEFORE INSERT ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_chain();
CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION reject_mutation();

CREATE TRIGGER platform_settings_immutable BEFORE UPDATE OR DELETE ON platform_settings
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "platform_settings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_settings")),
        sa.UniqueConstraint("version", name=op.f("uq_platform_settings_version")),
    )

    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("prev_hash", sa.LargeBinary(), nullable=True),
        sa.Column("hash", sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
        sa.UniqueConstraint("seq", name=op.f("uq_audit_log_seq")),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id", "at"])

    job_status = postgresql.ENUM(
        "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", name="job_status"
    )
    op.create_table(
        "jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("status", job_status, server_default="QUEUED", nullable=False),
        sa.Column("progress", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_ref", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name=op.f("ck_jobs_progress_range")),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.LargeBinary(), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_key"),
    )

    op.execute(AUDIT_FUNCTIONS)

    # Least privilege on append-only / immutable tables (default privileges grant DML).
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM {DML_ROLES}")
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON platform_settings FROM {DML_ROLES}")

    document = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    settings_table = sa.table(
        "platform_settings",
        sa.column("version", sa.Integer()),
        sa.column("values", postgresql.JSONB()),
        sa.column("reason", sa.Text()),
    )
    op.bulk_insert(
        settings_table,
        [{"version": 1, "values": document, "reason": "Initial defaults from spec section 6.2"}],
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS platform_settings_immutable ON platform_settings")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_chain ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_verify_chain()")
    op.execute("DROP FUNCTION IF EXISTS reject_mutation()")
    op.execute("DROP FUNCTION IF EXISTS audit_log_chain()")
    op.execute("DROP FUNCTION IF EXISTS audit_row_hash(bytea, audit_log)")
    op.drop_table("idempotency_keys")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("platform_settings")
