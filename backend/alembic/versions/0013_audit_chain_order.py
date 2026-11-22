"""Audit chain: number each row after taking the chain lock (fixes a fork under concurrency).

Found by the Phase 6 gate (DECISIONS D103). `audit_log.seq` is an identity column, so PostgreSQL
gave a row its number when the INSERT started, **before** `audit_log_chain()` took the chain's
advisory lock. Two requests writing at once could therefore take numbers in one order and the lock
in the other: row 5703 waited for the lock while 5704 chained and committed, then 5703 chained
after 5704, and the next row chained after 5704 again (the highest number). The chain forked and
`audit_verify_chain()`, which walks rows in `seq` order, reported tampering that never happened.

Now the trigger takes the next number from the column's own sequence *after* the lock, so the
numbering order and the chain order are the same by construction. The identity default still
draws a value first, which leaves gaps; the chain and its verification need order, not
contiguity. The function stays SECURITY DEFINER (0002) so it can read the latest hash under RLS.

Rows written before this migration keep their hashes (the log is append-only); a database whose
chain already forked keeps reporting that first break. Development and demo databases are reset
by `make demo-reset`; the test stack starts empty.

Revision ID: 0013_audit_chain_order
Revises: 0012_reputation_engine
Create Date: 2026-11-22 00:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_audit_chain_order"
down_revision: str | None = "0012_reputation_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FIXED = r"""
CREATE OR REPLACE FUNCTION audit_log_chain() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  last_hash bytea;
BEGIN
  -- Serialize chain extension so two concurrent inserts can't share a prev_hash.
  PERFORM pg_advisory_xact_lock(hashtext('devsync.audit_log.chain'));
  -- Number the row only now, under the lock: the chain order and the seq order are then the
  -- same, which is the order audit_verify_chain() walks (D103).
  NEW.seq := nextval(pg_get_serial_sequence('public.audit_log', 'seq'));
  NEW.at := coalesce(NEW.at, now());
  SELECT hash INTO last_hash FROM audit_log ORDER BY seq DESC LIMIT 1;
  NEW.prev_hash := last_hash;
  NEW.hash := audit_row_hash(last_hash, NEW);
  RETURN NEW;
END;
$$;
"""

ORIGINAL = r"""
CREATE OR REPLACE FUNCTION audit_log_chain() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
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
"""


def upgrade() -> None:
    op.execute(FIXED)


def downgrade() -> None:
    op.execute(ORIGINAL)
