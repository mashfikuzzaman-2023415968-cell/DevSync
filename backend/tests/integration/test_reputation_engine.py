"""The reputation engine against the real database (spec §9.1, §17 Phase 6; migration 0012).

Stored values equal the pure engine's; recalculation is idempotent; the D48 "seeded" marker turns
off for computed snapshots; per-skill competency covers the scored domains; a developer without
history keeps the on-the-fly newcomer values; the verified certificate counts for Γ⁰ (D94); the
platform-mean newcomer β follows D98; and the whole recalculation is audited.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.algorithms.reputation import compute_snapshot
from app.core.config import Environment
from app.db.context import DbContext
from app.db.session import open_session
from app.models.foundation import AuditLog
from app.models.profiles import (
    Certificate,
    FileKind,
    Skill,
    SkillDomain,
    StoredFile,
    VerificationStatus,
)
from app.models.reputation import (
    ReputationHistory,
    ReputationLog,
    ReputationSkill,
    ReputationSnapshot,
    ReputationSource,
)
from app.schemas.platform_settings import PlatformSettingsValues, RepSettings
from app.services import reputation_engine, reputation_inputs, reputation_read
from tests.helpers import stack_available
from tests.integration.test_rls_bids import make_user

pytestmark = pytest.mark.integration
D = Decimal
SETTINGS = PlatformSettingsValues()
VERSION = 41  # any settings version number; stored with every computed value


@pytest.fixture(autouse=True)
def _stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)


def _row(dev: uuid.UUID, n: int, domain: SkillDomain, client: str, t: int) -> ReputationHistory:
    return ReputationHistory(
        developer_id=dev, source=ReputationSource.SIMULATED, project_label=f"Project {n}",
        client_key=client, domain=domain, t_days=t, deadline_days=30,
        gamma_comm=D("0.8"), gamma_team=D("0.7"), internal_slots=[D("0.75"), D("1")],
        external_slots=[D("0.5")] if n % 2 == 0 else [],
        completed_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=30 * n), sim_version=1,
    )  # fmt: skip


async def _with_history(projects: int) -> uuid.UUID:
    dev = await make_user("DEVELOPER")
    domains = [SkillDomain.FRONTEND, SkillDomain.BACKEND, SkillDomain.DATABASE]
    async with open_session(DbContext.system(), job=True) as db:
        for n in range(projects):
            db.add(_row(dev, n, domains[n % 3], f"client-{n % 2}", 15 + n))
        await db.commit()
    return dev


async def _recalc(dev: uuid.UUID, settings: PlatformSettingsValues = SETTINGS) -> int:
    async with open_session(DbContext.system(), job=True) as db:
        outcome = await reputation_engine.recalculate(db, dev, settings, VERSION, D("0.6"))
        await db.commit()
    assert outcome is not None
    return outcome.log_rows_added


async def test_stored_snapshot_equals_the_pure_engine_and_is_not_seeded() -> None:
    dev = await _with_history(4)
    added = await _recalc(dev)
    assert added == 4 * 8  # one row per parameter per project
    async with open_session(DbContext.system(), job=True) as db:
        rows = await reputation_inputs.load_history(db, dev)
        ev = await reputation_inputs.evidence(db, dev, SETTINGS)
        params = reputation_inputs.params_from_settings(SETTINGS, D("0.6"))
        expected = compute_snapshot([reputation_inputs.to_record(r) for r in rows], params, ev)
        stored = await db.scalar(
            select(ReputationSnapshot).where(ReputationSnapshot.developer_id == dev)
        )
        view = await reputation_read.read_one(db, dev, SETTINGS)
        assert stored is not None
        e = expected.snapshot
        got = (stored.omega, stored.x, stored.xm, stored.beta, stored.mu, stored.t, stored.c,
               stored.p, stored.completed_projects, stored.settings_version)  # fmt: skip
    assert got == (e.omega, e.x, e.xm, e.beta, e.mu, e.t, e.c, e.p, 4, VERSION)
    assert view.seeded is False
    assert view.is_newcomer is False
    assert view.p == pytest.approx(float(e.p))


async def test_recalculation_is_idempotent() -> None:
    dev = await _with_history(3)
    assert await _recalc(dev) == 24
    assert await _recalc(dev) == 0  # same history + settings → no new log rows
    async with open_session(DbContext.system(), job=True) as db:
        count = await db.scalar(
            select(func.count()).select_from(ReputationLog).where(ReputationLog.developer_id == dev)
        )
        snaps = await db.scalar(
            select(func.count())
            .select_from(ReputationSnapshot)
            .where(ReputationSnapshot.developer_id == dev)
        )
    assert count == 24
    assert snaps == 1


async def test_a_new_project_adds_only_its_own_log_rows() -> None:
    dev = await _with_history(2)
    assert await _recalc(dev) == 16
    async with open_session(DbContext.system(), job=True) as db:
        db.add(_row(dev, 7, SkillDomain.DATA, "client-9", 20))
        await db.commit()
    assert await _recalc(dev) == 8


async def test_skill_competency_rows_cover_the_scored_domains() -> None:
    dev = await _with_history(3)  # FRONTEND, BACKEND, DATABASE
    await _recalc(dev)
    async with open_session(DbContext.system(), job=True) as db:
        domains = await db.scalars(
            select(Skill.domain)
            .join(ReputationSkill, ReputationSkill.skill_id == Skill.id)
            .where(ReputationSkill.developer_id == dev)
            .distinct()
        )
        found = {d.value for d in domains.all()}
    assert found == {"FRONTEND", "BACKEND", "DATABASE"}


async def test_replication_mode_stores_no_skill_competency() -> None:
    dev = await _with_history(3)
    replication = PlatformSettingsValues.model_validate({"algorithm": {"mode": "pcs_replication"}})
    await _recalc(dev, replication)
    async with open_session(DbContext.system(), job=True) as db:
        n = await db.scalar(
            select(func.count())
            .select_from(ReputationSkill)
            .where(ReputationSkill.developer_id == dev)
        )
    assert n == 0


async def test_developer_without_history_stores_nothing_and_stays_a_computed_newcomer() -> None:
    dev = await make_user("DEVELOPER")
    async with open_session(DbContext.system(), job=True) as db:
        assert await reputation_engine.recalculate(db, dev, SETTINGS, VERSION, D("0.6")) is None
        assert (
            await db.scalar(
                select(ReputationSnapshot).where(ReputationSnapshot.developer_id == dev)
            )
            is None
        )
        view = await reputation_read.read_one(db, dev, SETTINGS)
    assert view.is_newcomer is True
    assert view.completed_projects == 0


async def test_verified_certificate_counts_for_gamma0() -> None:
    """D94: phone + email + profile + verified certificate = 4 items (a pending one doesn't)."""
    dev = await make_user("DEVELOPER")
    async with open_session(DbContext.system(), job=True) as db:
        before = await reputation_inputs.verified_items(db, dev)
        stored = StoredFile(owner_id=dev, kind=FileKind.CERTIFICATE, storage_key=uuid.uuid4(),
                            original_name="c.pdf", mime_type="application/pdf", size_bytes=5,
                            sha256="0" * 64)  # fmt: skip
        db.add(stored)
        await db.flush()
        file_id = stored.id
        db.add(Certificate(user_id=dev, title="AWS", issuer="Amazon", file_id=file_id,
                           status=VerificationStatus.PENDING))  # fmt: skip
        await db.commit()
    async with open_session(DbContext.system(), job=True) as db:
        assert await reputation_inputs.verified_items(db, dev) == before  # pending: no
        cert = await db.scalar(select(Certificate).where(Certificate.user_id == dev))
        assert cert is not None
        cert.status = VerificationStatus.VERIFIED
        await db.commit()
    async with open_session(DbContext.system(), job=True) as db:
        assert await reputation_inputs.verified_items(db, dev) == before + 1


async def test_newcomer_review_setting_wins_over_the_platform_mean() -> None:
    settings = PlatformSettingsValues(rep=RepSettings(newcomer_review=D("0.77")))
    async with open_session(DbContext.system(), job=True) as db:
        assert await reputation_inputs.newcomer_review(db, settings) == D("0.77")
        devs = await reputation_engine.developers_with_history(db)
        assert await reputation_engine.resolve_newcomer_review(db, devs, settings) == D("0.77")


async def test_platform_mean_ignores_seeded_snapshots() -> None:
    """D98: only engine-computed snapshots (settings_version set) of experienced developers
    count; a hand-set (seeded) β of 0.05 changes nothing."""
    dev = await make_user("DEVELOPER")
    async with open_session(DbContext.system(), job=True) as db:
        before = await reputation_inputs.newcomer_review(db, SETTINGS)
        half = D("0.5")
        db.add(ReputationSnapshot(developer_id=dev, omega=half, x=half, xm=half, beta=D("0.05"),
                                  mu=half, t=half, c=half, p=D("0.3"), completed_projects=9,
                                  distinct_clients=3))  # fmt: skip
        await db.commit()
    async with open_session(DbContext.system(), job=True) as db:
        assert await reputation_inputs.newcomer_review(db, SETTINGS) == before


async def test_recalculate_all_is_deterministic_and_audited() -> None:
    await _with_history(3)
    await _with_history(5)
    async with open_session(DbContext.system(), job=True) as db:
        first = await reputation_engine.recalculate_all(db, SETTINGS, VERSION)
        await db.commit()
    async with open_session(DbContext.system(), job=True) as db:
        snaps_before = (await db.execute(
            select(ReputationSnapshot.developer_id, ReputationSnapshot.p)
            .where(ReputationSnapshot.settings_version == VERSION)
        )).all()  # fmt: skip
        second = await reputation_engine.recalculate_all(db, SETTINGS, VERSION)
        await db.commit()
        snaps_after = (await db.execute(
            select(ReputationSnapshot.developer_id, ReputationSnapshot.p)
            .where(ReputationSnapshot.settings_version == VERSION)
        )).all()  # fmt: skip
        audits = await db.scalar(
            select(func.count()).select_from(AuditLog)
            .where(AuditLog.action == "reputation.recalculate_all")
        )  # fmt: skip
    assert first.developers >= 2
    assert second.log_rows_added == 0
    assert second.newcomer_review == first.newcomer_review
    assert sorted(snaps_before) == sorted(snaps_after)
    assert audits is not None
    assert audits >= 2
