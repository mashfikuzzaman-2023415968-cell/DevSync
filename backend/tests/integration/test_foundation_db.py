"""Migration, append-only audit log with hash chain, grants and settings versions (Phase 0).

Runs inside the test compose stack (needs MIGRATION_DATABASE_URL and DATABASE_URL).
"""

from __future__ import annotations

from typing import Any

import pytest
from app.core.audit import verify_chain, write_audit
from app.schemas.platform_settings import default_settings_document
from app.services import platform_settings
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

pytestmark = pytest.mark.integration


def test_migration_downgrade_and_upgrade_round_trip(migrated: str) -> None:
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(migrated)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT max(version) FROM platform_settings")).scalar_one() == 1
    engine.dispose()


async def test_seeded_settings_are_active(app_session: Any) -> None:
    version, values = await platform_settings.get_active(app_session)
    assert version >= 1
    assert values.model_dump(mode="json") == default_settings_document()


async def test_create_version_writes_row_and_audit(app_session: Any) -> None:
    doc = default_settings_document()
    doc["pay"]["auto_approve_days"] = 5  # type: ignore[index]
    new = await platform_settings.create_version(
        app_session, doc, reason="Shorter auto-approval for demo", changed_by=None
    )
    version, values = await platform_settings.get_active(app_session)
    assert version == new
    assert values.pay.auto_approve_days == 5
    count = (
        await app_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action='settings.update' AND entity_id=:v"),
            {"v": str(new)},
        )
    ).scalar_one()
    assert count == 1


async def test_create_version_rejects_invalid_and_short_reason(app_session: Any) -> None:
    from app.core.errors import SettingsValidationError  # noqa: PLC0415

    doc = default_settings_document()
    doc["rep"]["kappa_ext"] = "0.4"  # type: ignore[index]
    with pytest.raises(SettingsValidationError):
        await platform_settings.create_version(
            app_session, doc, reason="valid reason here", changed_by=None
        )
    with pytest.raises(SettingsValidationError):
        await platform_settings.create_version(
            app_session, default_settings_document(), reason="short", changed_by=None
        )


async def test_audit_rows_are_hash_chained(app_session: Any) -> None:
    for i in range(3):
        await write_audit(
            app_session, action="test.event", entity_type="thing", entity_id=str(i), after={"i": i}
        )
    rows = (
        await app_session.execute(
            text("SELECT prev_hash, hash FROM audit_log ORDER BY seq DESC LIMIT 3")
        )
    ).all()
    assert rows[0].prev_hash == rows[1].hash
    assert rows[1].prev_hash == rows[2].hash
    assert await verify_chain(app_session) is None


async def test_audit_redacts_secrets_in_before_after(app_session: Any) -> None:
    await write_audit(
        app_session, action="t.x", entity_type="t", entity_id=None, after={"password": "p", "ok": 1}
    )
    after = (
        await app_session.execute(text("SELECT after FROM audit_log ORDER BY seq DESC LIMIT 1"))
    ).scalar_one()
    assert after == {"password": "[REDACTED]", "ok": 1}


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log", "TRUNCATE audit_log"],
)
async def test_app_role_cannot_mutate_audit_log(app_session: Any, statement: str) -> None:
    await write_audit(app_session, action="t.y", entity_type="t", entity_id=None)
    with pytest.raises((ProgrammingError, DBAPIError)):
        await app_session.execute(text(statement))


@pytest.mark.parametrize(
    "statement", ["UPDATE platform_settings SET reason = 'x'", "DELETE FROM platform_settings"]
)
async def test_app_role_cannot_mutate_settings(app_session: Any, statement: str) -> None:
    with pytest.raises((ProgrammingError, DBAPIError)):
        await app_session.execute(text(statement))


def test_trigger_blocks_mutation_even_for_owner(migrated: str) -> None:
    engine = create_engine(migrated)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO audit_log (action, entity_type) VALUES ('t.owner', 't')"))
    with engine.connect() as conn, pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("UPDATE audit_log SET action = 'forged'"))
    engine.dispose()


def test_tampering_is_detected_by_chain_verification(migrated: str) -> None:
    """Simulate an attacker with owner rights who disables the trigger and edits a row."""
    engine = create_engine(migrated)
    with engine.connect() as conn:
        tx = conn.begin()
        conn.execute(
            text("INSERT INTO audit_log (action, entity_type) VALUES ('t.a', 't'), ('t.b', 't')")
        )
        assert conn.execute(text("SELECT audit_verify_chain()")).scalar_one() is None
        conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only"))
        target = conn.execute(
            text("SELECT seq FROM audit_log ORDER BY seq DESC LIMIT 1 OFFSET 1")
        ).scalar_one()
        conn.execute(text("UPDATE audit_log SET action = 'forged' WHERE seq = :s"), {"s": target})
        assert conn.execute(text("SELECT audit_verify_chain()")).scalar_one() == target
        tx.rollback()
    engine.dispose()


def test_app_role_has_no_ddl(migrated: str, app_db_url: str) -> None:
    sync_url = app_db_url.replace("+asyncpg", "+psycopg")
    engine = create_engine(sync_url)
    with engine.connect() as conn, pytest.raises((ProgrammingError, DBAPIError)):
        conn.execute(text("CREATE TABLE should_fail (id int)"))
    engine.dispose()
