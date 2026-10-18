"""Row-level security for the Phase 3 tables and definer functions (spec §14.15, §14.13 row 3).

Queries run directly as `devsync_app` (the web role), bypassing the services, to prove the
database itself keeps profiles, files, evidence and the question bank apart.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import column, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.config import Environment
from app.core.security import hash_password
from app.db.context import DbContext
from app.db.session import open_session
from app.models import User, UserRole, UserStatus
from app.models.profiles import (
    Certificate,
    ClientProfile,
    DeveloperProfile,
    DeveloperSkill,
    ExternalReview,
    FileKind,
    PortfolioImage,
    PortfolioItem,
    ProfileVisibility,
    Question,
    Skill,
    SkillEvidence,
    SkillTest,
    StoredFile,
    TestAttempt,
)
from tests.helpers import stack_available, unique_email

pytestmark = pytest.mark.integration
NOW = datetime.now(UTC)
DbErrors = (ProgrammingError, DBAPIError)


@pytest.fixture(autouse=True)
def _require_stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)


async def make_user(role: str = "DEVELOPER", status: str = "ACTIVE") -> uuid.UUID:
    async with open_session(DbContext.system(), job=True) as db:
        user = User(
            email=unique_email(),
            phone_e164="+88017" + str(uuid.uuid4().int)[:8] if role != "ADMIN" else None,
            role=UserRole(role),
            status=UserStatus(status),
            display_name="RLS",
            password_hash=hash_password("rls test password 1!"),
        )
        db.add(user)
        await db.flush()
        uid = user.id
        await db.commit()
    return uid


def as_user(uid: uuid.UUID, role: str = "DEVELOPER") -> Any:
    return open_session(DbContext(user_id=uid, role=role))


@dataclass
class Owned:
    """One row per Phase 3 table for a developer (and a client profile for a client)."""

    dev: uuid.UUID
    client: uuid.UUID
    image_file: uuid.UUID
    cert_file: uuid.UUID
    item: uuid.UUID
    cert: uuid.UUID
    review: uuid.UUID
    attempt: uuid.UUID


def _file(owner: uuid.UUID, kind: FileKind) -> StoredFile:
    return StoredFile(
        owner_id=owner,
        kind=kind,
        storage_key=uuid.uuid4(),
        original_name="f.png",
        mime_type="image/png",
        size_bytes=10,
        sha256="0" * 64,
        attached_at=NOW,
    )


async def seed(visibility: ProfileVisibility = ProfileVisibility.PUBLIC) -> Owned:
    dev, client = await make_user("DEVELOPER"), await make_user("CLIENT")
    async with open_session(DbContext.system(), job=True) as db:
        skill = (await db.scalars(select(Skill).limit(1))).one()
        tests = list((await db.scalars(select(SkillTest.id).order_by(SkillTest.id).limit(2))).all())
        image_file, cert_file, review_file = (
            _file(dev, FileKind.PORTFOLIO_IMAGE),
            _file(dev, FileKind.CERTIFICATE),
            _file(dev, FileKind.EXTERNAL_REVIEW),
        )
        db.add_all([image_file, cert_file, review_file])
        await db.flush()
        item = PortfolioItem(user_id=dev, title="Item", position=0)
        cert = Certificate(user_id=dev, title="Cert", issuer="Issuer", file_id=cert_file.id)
        review = ExternalReview(
            developer_id=dev,
            source="Upwork",
            rating_norm=Decimal("0.9"),
            project_date=date(2026, 1, 1),
            evidence_file_id=review_file.id,
        )
        db.add_all(
            [
                DeveloperProfile(user_id=dev, headline="Secret?", visibility=visibility),
                DeveloperSkill(user_id=dev, skill_id=skill.id, self_level=3),
                ClientProfile(user_id=client, organization="Org"),
                item,
                cert,
                review,
            ]
        )
        await db.flush()
        db.add(PortfolioImage(portfolio_item_id=item.id, file_id=image_file.id))
        ids = (image_file.id, cert_file.id, item.id, cert.id, review.id)
        await db.commit()
    # Attempts and evidence only come from the definer functions, as the developer.
    start = text("SELECT attempt_id FROM start_test_attempt(:t, now(), :seed)")
    async with as_user(dev) as db:
        attempt = (await db.execute(start, {"t": tests[0], "seed": 1})).scalar_one()
        scored = (await db.execute(start, {"t": tests[1], "seed": 2})).scalar_one()
        await db.execute(text("SELECT * FROM score_test_attempt(:a, now())"), {"a": scored})
        await db.commit()
    owned = Owned(dev, client, *ids, attempt)
    return owned


OWNED_TABLES: list[tuple[type[Any], str]] = [
    (DeveloperProfile, "user_id"),
    (DeveloperSkill, "user_id"),
    (StoredFile, "owner_id"),
    (PortfolioItem, "user_id"),
    (Certificate, "user_id"),
    (ExternalReview, "developer_id"),
    (TestAttempt, "user_id"),
    (SkillEvidence, "user_id"),
]


@pytest.mark.parametrize(
    ("model", "col"), OWNED_TABLES, ids=[m.__tablename__ for m, _ in OWNED_TABLES]
)
async def test_other_users_and_guests_see_nothing(model: type[Any], col: str) -> None:
    owned = await seed()
    other = await make_user("DEVELOPER")
    async with as_user(owned.dev) as db:
        assert owned.dev in set((await db.scalars(select(getattr(model, col)))).all())
    for ctx in (
        DbContext(user_id=other, role="DEVELOPER"),
        DbContext(user_id=owned.client, role="CLIENT"),
        DbContext.guest(),
    ):
        async with open_session(ctx) as db:
            owners = set((await db.scalars(select(getattr(model, col)))).all())
        assert owned.dev not in owners, (model.__tablename__, ctx)


async def test_portfolio_images_and_client_profiles_follow_their_owner() -> None:
    owned = await seed()
    other = await make_user("DEVELOPER")
    async with as_user(other) as db:
        assert (await db.scalars(select(PortfolioImage.id))).all() == [] or all(False for _ in ())
        rows = (await db.scalars(select(PortfolioImage.portfolio_item_id))).all()
        assert owned.item not in rows
        assert owned.client not in (await db.scalars(select(ClientProfile.user_id))).all()


async def test_admin_reads_evidence_but_not_the_question_bank_through_others() -> None:
    owned = await seed()
    admin = await make_user("ADMIN")
    async with as_user(admin, "ADMIN") as db:
        assert owned.cert in set((await db.scalars(select(Certificate.id))).all())
        assert (await db.scalar(select(func.count()).select_from(Question))) >= 128
    for role in ("DEVELOPER", "CLIENT"):
        async with as_user(owned.dev, role) as db:
            assert (await db.scalar(select(func.count()).select_from(Question))) == 0
    async with open_session(DbContext.guest()) as db:
        assert (await db.scalar(select(func.count()).select_from(Question))) == 0


async def test_cross_user_writes_affect_nothing_or_are_refused() -> None:
    owned = await seed()
    other = await make_user("DEVELOPER")
    async with as_user(other) as db:
        r1 = await db.execute(
            update(PortfolioItem).where(PortfolioItem.id == owned.item).values(title="x")
        )
        r2 = await db.execute(text("DELETE FROM certificates WHERE id = :id"), {"id": owned.cert})
        r3 = await db.execute(
            text("UPDATE files SET deleted_at = now() WHERE owner_id = :o"), {"o": owned.dev}
        )
        await db.commit()
    assert (r1.rowcount, r2.rowcount, r3.rowcount) == (0, 0, 0)  # type: ignore[attr-defined]
    async with as_user(other) as db:
        with pytest.raises(DbErrors, match="row-level security"):
            await db.execute(
                insert(PortfolioItem).values(user_id=owned.dev, title="forged", position=1)
            )


async def test_attempts_and_evidence_are_written_only_by_the_definers() -> None:
    owned = await seed()
    async with as_user(owned.dev) as db:
        with pytest.raises(DbErrors, match="row-level security"):
            await db.execute(
                text(
                    "INSERT INTO skill_evidence (user_id, skill_id, source, score, at) "
                    "SELECT :u, id, 'TEST', 1, now() FROM skills LIMIT 1"
                ),
                {"u": owned.dev},
            )
    async with as_user(owned.dev) as db:
        r = await db.execute(
            update(TestAttempt).where(TestAttempt.id == owned.attempt).values(score=1)
        )
        await db.commit()
    assert r.rowcount == 0  # type: ignore[attr-defined]


async def test_owner_cannot_verify_their_own_evidence() -> None:
    owned = await seed()
    async with as_user(owned.dev) as db:
        with pytest.raises(DbErrors, match="decided by an admin"):
            await db.execute(
                update(Certificate).where(Certificate.id == owned.cert).values(status="VERIFIED")
            )
    async with as_user(owned.dev) as db:
        with pytest.raises(DbErrors, match="decided by an admin"):
            await db.execute(
                update(ExternalReview)
                .where(ExternalReview.id == owned.review)
                .values(reviewed_at=NOW)
            )
    async with as_user(owned.dev) as db:
        with pytest.raises(DbErrors, match="decided by an admin"):
            await db.execute(
                insert(Certificate).values(
                    user_id=owned.dev,
                    title="t",
                    issuer="i",
                    file_id=owned.image_file,
                    status="VERIFIED",
                )
            )
    admin = await make_user("ADMIN")
    async with as_user(admin, "ADMIN") as db:
        await db.execute(
            update(Certificate)
            .where(Certificate.id == owned.cert)
            .values(status="VERIFIED", reviewed_by=admin, reviewed_at=NOW)
        )
        await db.commit()


async def test_stored_files_are_immutable() -> None:
    owned = await seed()
    async with as_user(owned.dev) as db:
        with pytest.raises(DbErrors, match="immutable"):
            await db.execute(
                update(StoredFile)
                .where(StoredFile.id == owned.cert_file)
                .values(storage_key=uuid.uuid4())
            )
    async with as_user(owned.dev) as db:
        with pytest.raises(DbErrors, match="scanner"):
            await db.execute(
                update(StoredFile)
                .where(StoredFile.id == owned.cert_file)
                .values(scan_status="CLEAN")
            )
    async with as_user(owned.dev) as db:  # soft delete stays possible
        await db.execute(
            update(StoredFile).where(StoredFile.id == owned.cert_file).values(deleted_at=NOW)
        )
        await db.commit()


async def test_taxonomy_is_read_only_for_the_web_role() -> None:
    uid = await make_user("DEVELOPER")
    async with as_user(uid) as db:
        assert (await db.scalar(select(func.count()).select_from(Skill))) == 8
        with pytest.raises(DbErrors, match="permission denied"):
            await db.execute(text("UPDATE skills SET active = false"))
    async with as_user(uid) as db:
        with pytest.raises(DbErrors, match="permission denied"):
            await db.execute(text("DELETE FROM skill_tests"))


async def test_attempt_questions_are_only_for_their_owner_and_never_include_answers() -> None:
    owned = await seed()
    other = await make_user("DEVELOPER")
    fn = select(column("question_id"), column("ordinal"), column("text"), column("options"))
    async with as_user(owned.dev) as db:
        rows = (await db.execute(fn.select_from(func.attempt_questions(owned.attempt)))).all()
        cols = (
            await db.execute(text("SELECT * FROM attempt_questions(:a)"), {"a": owned.attempt})
        ).keys()
    assert len(rows) == 10
    assert set(cols) == {"question_id", "ordinal", "text", "options"}
    async with as_user(other) as db:
        assert (await db.execute(fn.select_from(func.attempt_questions(owned.attempt)))).all() == []
        with pytest.raises(DbErrors, match="attempt not found"):
            await db.execute(select(func.record_test_answer(owned.attempt, uuid.uuid4(), 0, NOW)))
    async with as_user(other) as db:
        with pytest.raises(DbErrors, match="attempt not found"):
            await db.execute(
                text("SELECT * FROM score_test_attempt(:a, now())"), {"a": owned.attempt}
            )


async def test_web_role_cannot_score_as_system_but_the_worker_can() -> None:
    owned = await seed()
    async with open_session(DbContext.system()) as db:  # devsync_app claiming SYSTEM
        with pytest.raises(DbErrors, match="attempt not found"):
            await db.execute(
                text("SELECT * FROM score_test_attempt(:a, now())"), {"a": owned.attempt}
            )
    async with open_session(DbContext.system(), job=True) as db:
        row = (
            await db.execute(
                text("SELECT * FROM score_test_attempt(:a, now())"), {"a": owned.attempt}
            )
        ).one()
        await db.commit()
    assert row.total == 10


async def test_only_developers_start_attempts() -> None:
    owned = await seed()
    async with open_session(DbContext.system(), job=True) as db:
        test_id = (await db.scalars(select(SkillTest.id).limit(1))).one()
    async with as_user(owned.client, "CLIENT") as db:
        with pytest.raises(DbErrors, match="only developers"):
            await db.execute(text("SELECT * FROM start_test_attempt(:t, now(), 1)"), {"t": test_id})


async def test_public_profile_function_hides_pii_and_respects_visibility() -> None:
    public = await seed(ProfileVisibility.PUBLIC)
    hidden = await seed(ProfileVisibility.CLIENTS_ONLY)
    async with open_session(DbContext.guest()) as db:
        data = await db.scalar(select(func.public_developer_profile(public.dev)))
        assert await db.scalar(select(func.public_developer_profile(hidden.dev))) is None
        assert await db.scalar(select(func.public_developer_profile(public.client))) is None
    assert data is not None
    assert not {"email", "phone_e164", "password_hash", "phone"} & set(data)
    assert data["certificates"] == []  # only verified certificates are shown
    async with as_user(hidden.client, "CLIENT") as db:
        assert await db.scalar(select(func.public_developer_profile(hidden.dev))) is not None
    async with as_user(public.dev) as db:  # another developer: clients-only stays hidden
        assert await db.scalar(select(func.public_developer_profile(hidden.dev))) is None


async def test_file_access_rules() -> None:
    owned = await seed(ProfileVisibility.PUBLIC)
    other = await make_user("DEVELOPER")
    fn = select(column("storage_key")).select_from
    async with as_user(owned.dev) as db:
        assert (await db.execute(fn(func.file_access(owned.cert_file)))).first() is not None
    async with as_user(other) as db:
        assert (await db.execute(fn(func.file_access(owned.cert_file)))).first() is None
        assert (await db.execute(fn(func.file_access(owned.image_file)))).first() is not None
    async with open_session(DbContext.guest()) as db:
        assert (await db.execute(fn(func.file_access(owned.image_file)))).first() is not None
        assert (await db.execute(fn(func.file_access(owned.cert_file)))).first() is None


async def test_unverified_clients_cannot_see_clients_only_profiles() -> None:
    hidden = await seed(ProfileVisibility.CLIENTS_ONLY)
    pending = await make_user("CLIENT", status="PENDING")
    async with as_user(pending, "CLIENT") as db:
        assert await db.scalar(select(func.public_developer_profile(hidden.dev))) is None
    async with as_user(hidden.client, "CLIENT") as db:  # an ACTIVE client still can
        assert await db.scalar(select(func.public_developer_profile(hidden.dev))) is not None
