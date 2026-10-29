"""`make demo-reset` (scripts/demo_reset.py): user data goes, catalog data stays (D73, D75)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from scripts.demo_reset import PRESERVED, reset

pytestmark = pytest.mark.integration

# Tables whose rows belong to users (or their projects): the reset is meant to empty them.
USER_SCOPED = {
    "audit_log", "availability_reservations", "bids", "certificates", "client_profiles",
    "developer_profiles", "developer_skills", "devices_seen", "email_tokens", "external_reviews",
    "files", "idempotency_keys", "jobs", "notifications", "otp_codes", "plan_baselines",
    "plan_change_requests", "portfolio_items", "projects", "recovery_codes",
    "reputation_snapshots", "sessions", "skill_evidence", "test_attempts", "totp_credentials",
    "user_accommodations",
}  # fmt: skip

REFERENCING_USERS = text(
    "SELECT DISTINCT tc.table_name FROM information_schema.table_constraints tc "
    "JOIN information_schema.constraint_column_usage ccu "
    "ON ccu.constraint_name = tc.constraint_name "
    "WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'users'"
)
CATALOG_COUNTS = text(
    "SELECT (SELECT count(*) FROM question_bank), (SELECT count(*) FROM skills), "
    "(SELECT count(*) FROM competencies), (SELECT count(*) FROM platform_settings)"
)


def test_every_table_that_references_users_is_classified(migrated: str) -> None:
    """A new table with a foreign key to users would be emptied by the cascade: it must be
    either user data or a preserved catalog table, decided on purpose."""
    engine = create_engine(migrated)
    with engine.connect() as conn:
        tables = {row[0] for row in conn.execute(REFERENCING_USERS)}
    engine.dispose()
    assert tables - USER_SCOPED == set(PRESERVED)


def test_reset_keeps_the_catalog_and_empties_user_data(migrated: str) -> None:
    engine = create_engine(migrated)
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            before = conn.execute(CATALOG_COUNTS).one()
            assert before[0] > 0
            reset(conn)
            assert conn.execute(CATALOG_COUNTS).one() == before
            assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
            unlinked = "SELECT count(*) FROM question_bank WHERE reviewed_by_user IS NOT NULL"
            assert conn.execute(text(unlinked)).scalar_one() == 0
        finally:
            tx.rollback()  # the test database keeps its users
    engine.dispose()
