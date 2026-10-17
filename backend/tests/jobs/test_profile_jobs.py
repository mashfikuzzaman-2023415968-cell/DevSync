"""Orphan-upload cleanup and auto-scoring of expired attempts (spec §11, §14.9, §17 Phase 3)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.core.security import hash_password
from app.db.context import DbContext
from app.db.session import open_session
from app.models import User, UserRole, UserStatus
from app.models.profiles import (
    Certificate,
    FileKind,
    SkillEvidence,
    SkillTest,
    StoredFile,
    TestAttempt,
)
from app.services import files, skill_tests
from app.uploads.storage import Storage
from tests.helpers import stack_available, unique_email

pytestmark = pytest.mark.jobs
NOW = datetime.now(UTC)


@pytest.fixture(autouse=True)
def _stack(migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")


async def make_developer() -> uuid.UUID:
    async with open_session(DbContext.system(), job=True) as db:
        user = User(email=unique_email(), phone_e164="+88017" + str(uuid.uuid4().int)[:8],
                    role=UserRole.DEVELOPER, status=UserStatus.ACTIVE, display_name="Jobs",
                    password_hash=hash_password("jobs test password 1!"))  # fmt: skip
        db.add(user)
        await db.flush()
        uid = user.id
        await db.commit()
    return uid


def age(path: Path, delta: timedelta) -> None:
    t = (NOW - delta).timestamp()
    os.utime(path, (t, t))


async def file_row(store: Storage, owner: uuid.UUID, *, attached: bool, deleted: bool = False,
                   created: datetime = NOW) -> tuple[uuid.UUID, Path]:  # fmt: skip
    key = store.save(b"bytes")
    async with open_session(DbContext.system(), job=True) as db:
        row = StoredFile(owner_id=owner, kind=FileKind.CERTIFICATE, storage_key=key,
                         original_name="c.pdf", mime_type="application/pdf", size_bytes=5,
                         sha256="0" * 64, attached_at=NOW if attached else None,
                         deleted_at=NOW if deleted else None, created_at=created)  # fmt: skip
        db.add(row)
        await db.flush()
        file_id = row.id
        await db.commit()
    age(store.path_for(key), NOW - created + timedelta(seconds=1))
    return file_id, store.path_for(key)


async def test_purge_removes_deleted_unattached_and_unknown_files(tmp_path: Path) -> None:
    store = Storage(str(tmp_path / "uploads"))
    owner = await make_developer()
    old = NOW - timedelta(hours=25)
    kept_id, kept = await file_row(store, owner, attached=True, created=old)
    fresh_id, fresh = await file_row(store, owner, attached=False)  # < 24 h: still uploading
    _stale_id, stale = await file_row(store, owner, attached=False, created=old)
    _gone_id, gone = await file_row(store, owner, attached=True, deleted=True)
    unknown_old = store.path_for(store.save(b"no row"))
    age(unknown_old, timedelta(hours=25))
    unknown_new = store.path_for(store.save(b"no row yet"))
    store.tmp.mkdir(parents=True, exist_ok=True)
    incoming = store.tmp / "partial"
    incoming.write_bytes(b"x")
    age(incoming, timedelta(hours=2))
    (store.root / "not-a-key.txt").write_bytes(b"left alone")
    async with open_session(DbContext.system(), job=True) as db:
        counts = await files.purge_orphans(db, store, NOW)
    assert counts["rows"] >= 2
    assert counts["orphan_bytes"] >= 1
    assert counts["incoming"] == 1
    assert kept.exists()
    assert fresh.exists()
    assert unknown_new.exists()
    assert (store.root / "not-a-key.txt").exists()
    for path in (stale, gone, unknown_old, incoming):
        assert not path.exists(), path
    async with open_session(DbContext.system(), job=True) as db:
        ids = set(
            (await db.scalars(select(StoredFile.id).where(StoredFile.owner_id == owner))).all()
        )
    assert ids == {kept_id, fresh_id}


async def test_purge_keeps_rows_that_are_still_referenced(tmp_path: Path) -> None:
    store = Storage(str(tmp_path / "uploads"))
    owner = await make_developer()
    file_id, path = await file_row(store, owner, attached=True, deleted=True)
    async with open_session(DbContext.system(), job=True) as db:
        db.add(Certificate(user_id=owner, title="Still here", issuer="I", file_id=file_id))
        await db.commit()
    async with open_session(DbContext.system(), job=True) as db:
        counts = await files.purge_orphans(db, store, NOW)
    assert counts["skipped"] >= 1
    assert path.exists()


async def test_purge_with_an_empty_store(tmp_path: Path) -> None:
    async with open_session(DbContext.system(), job=True) as db:
        counts = await files.purge_orphans(db, Storage(str(tmp_path / "none")), NOW)
    assert counts["orphan_bytes"] == 0
    assert counts["incoming"] == 0


async def test_expired_attempts_are_scored_once_with_evidence() -> None:
    dev = await make_developer()
    async with open_session(DbContext.system(), job=True) as db:
        test_id = (await db.scalars(select(SkillTest.id).limit(1))).one()
    started = NOW - timedelta(minutes=20)
    async with open_session(DbContext(user_id=dev, role="DEVELOPER")) as db:
        attempt_id = (await db.execute(
            text("SELECT attempt_id FROM start_test_attempt(:t, :now, 7)"),
            {"t": test_id, "now": started},
        )).scalar_one()  # fmt: skip
        await db.commit()
    async with open_session(DbContext.system(), job=True) as db:
        assert await skill_tests.score_expired_attempts(db, NOW) >= 1
    async with open_session(DbContext.system(), job=True) as db:
        attempt = (await db.scalars(select(TestAttempt).where(TestAttempt.id == attempt_id))).one()
        evidence = (await db.scalars(
            select(SkillEvidence).where(SkillEvidence.attempt_id == attempt_id)
        )).all()  # fmt: skip
        assert attempt.submitted_at is not None
        assert attempt.score == 0
        assert len(evidence) == 1
        # A second run finds nothing more to do for this attempt.
        await skill_tests.score_expired_attempts(db, NOW)
        again = (await db.scalars(
            select(SkillEvidence).where(SkillEvidence.attempt_id == attempt_id)
        )).all()  # fmt: skip
    assert len(again) == 1


async def test_open_attempts_within_their_time_are_left_alone() -> None:
    dev = await make_developer()
    async with open_session(DbContext.system(), job=True) as db:
        test_id = (await db.scalars(select(SkillTest.id).limit(1))).one()
    async with open_session(DbContext(user_id=dev, role="DEVELOPER")) as db:
        attempt_id = (await db.execute(
            text("SELECT attempt_id FROM start_test_attempt(:t, :now, 8)"),
            {"t": test_id, "now": NOW},
        )).scalar_one()  # fmt: skip
        await db.commit()
    async with open_session(DbContext.system(), job=True) as db:
        await skill_tests.score_expired_attempts(db, NOW + timedelta(minutes=5))
        attempt = (await db.scalars(select(TestAttempt).where(TestAttempt.id == attempt_id))).one()
        assert attempt.submitted_at is None
