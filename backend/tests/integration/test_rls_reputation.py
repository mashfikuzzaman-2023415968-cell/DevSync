"""Row-level security and append-only rules of the Phase 6 reputation tables (spec §14.15,
§14.13 row 6, §7.7 AO; migration 0012).

Queries run directly as the web role (`devsync_app`), bypassing the services, so the database
itself proves: history and the change log are private to the developer and admins; per-skill
competency is a public read; no web session can write any of them, even claiming SYSTEM; and the
log refuses UPDATE and DELETE for everyone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.config import Environment
from app.db.context import DbContext
from app.db.session import open_session
from app.models.profiles import Skill, SkillDomain
from app.models.reputation import (
    ReputationHistory,
    ReputationLog,
    ReputationSkill,
    ReputationSnapshot,
    ReputationSource,
)
from tests.helpers import stack_available
from tests.integration.test_rls_bids import as_user, make_user

pytestmark = pytest.mark.integration
DbErrors = (ProgrammingError, DBAPIError)


@pytest.fixture(autouse=True)
def _require_stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)


def _history(dev: uuid.UUID, label: str = "Simulated project 1") -> ReputationHistory:
    return ReputationHistory(
        developer_id=dev,
        source=ReputationSource.SIMULATED,
        project_label=label,
        client_key="client-001",
        domain=SkillDomain.FRONTEND,
        t_days=18,
        deadline_days=30,
        gamma_comm=Decimal("0.8"),
        gamma_team=Decimal("0.7"),
        internal_slots=[Decimal("0.75"), Decimal("1")],
        external_slots=[],
        completed_at=datetime(2026, 9, 1, tzinfo=UTC),
        sim_version=1,
    )


async def _seed(dev: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """One history row, one log row and one skill row for `dev`, written by SYSTEM."""
    async with open_session(DbContext.system(), job=True) as db:
        hist = _history(dev)
        db.add(hist)
        await db.flush()
        log = ReputationLog(
            developer_id=dev, history_id=hist.id, parameter="t", old=Decimal("0.5"),
            new=Decimal("0.4"), raw_new=Decimal("0.4"), inputs={"t_days": "18"},
            reason_code="ON_TIME", formula_version=1, settings_version=5,
        )  # fmt: skip
        skill_id = await db.scalar(select(Skill.id).where(Skill.name == "React"))
        db.add(log)
        db.add(ReputationSkill(developer_id=dev, skill_id=skill_id, competency=Decimal("0.6"),
                               settings_version=5))  # fmt: skip
        await db.flush()
        ids = hist.id, log.id
        await db.commit()
    return ids


async def _count(db: Any, model: Any, dev: uuid.UUID) -> int:
    rows = await db.scalars(select(model.id).where(model.developer_id == dev))
    return len(rows.all())


async def test_history_and_log_are_private_to_the_developer_and_admins() -> None:
    dev = await make_user("DEVELOPER")
    other = await make_user("DEVELOPER")
    client = await make_user("CLIENT")
    admin = await make_user("ADMIN")
    await _seed(dev)
    for model in (ReputationHistory, ReputationLog):
        async with as_user(dev, "DEVELOPER") as db:
            assert await _count(db, model, dev) == 1
        async with as_user(admin, "ADMIN") as db:
            assert await _count(db, model, dev) == 1
        async with as_user(other, "DEVELOPER") as db:
            assert await _count(db, model, dev) == 0
        async with as_user(client, "CLIENT") as db:
            assert await _count(db, model, dev) == 0
        async with open_session(DbContext.guest()) as db:
            assert await _count(db, model, dev) == 0


async def test_skill_competency_is_a_public_read_for_signed_in_users_only() -> None:
    dev = await make_user("DEVELOPER")
    other = await make_user("DEVELOPER")
    await _seed(dev)
    async with as_user(other, "DEVELOPER") as db:
        assert await _count(db, ReputationSkill, dev) == 1
    async with open_session(DbContext.guest()) as db:
        assert await _count(db, ReputationSkill, dev) == 0


async def test_web_role_cannot_write_reputation_even_claiming_system() -> None:
    """§14.13 row 6: inputs come only from server-side evidence. The developer can't insert
    their own history, and a web connection that sets app.role = SYSTEM gains nothing
    (`is_system()` checks the worker login role)."""
    dev = await make_user("DEVELOPER")
    for ctx in (DbContext(user_id=dev, role="DEVELOPER"), DbContext(user_id=dev, role="SYSTEM")):
        async with open_session(ctx) as db:
            db.add(_history(dev, label=f"forged {ctx.role}"))
            with pytest.raises(DbErrors):
                await db.flush()
        async with open_session(ctx) as db:
            db.add(ReputationSnapshot(developer_id=dev, omega="1", x="1", xm="1", beta="1",
                                      mu="1", t="1", c="1", p="1"))  # fmt: skip
            with pytest.raises(DbErrors):
                await db.flush()


async def test_reputation_log_is_append_only_even_for_system() -> None:
    """UPDATE and DELETE are refused for the worker too (trigger + no grant)."""
    dev = await make_user("DEVELOPER")
    _hist_id, log_id = await _seed(dev)
    async with open_session(DbContext.system(), job=True) as db:
        with pytest.raises(DbErrors):
            await db.execute(
                update(ReputationLog).where(ReputationLog.id == log_id).values(new=Decimal(1))
            )
    async with open_session(DbContext.system(), job=True) as db:
        with pytest.raises(DbErrors):
            await db.execute(delete(ReputationLog).where(ReputationLog.id == log_id))
    async with open_session(DbContext.system(), job=True) as db:
        with pytest.raises(DbErrors):
            await db.execute(text("TRUNCATE reputation_log"))


async def test_log_entries_are_unique_per_project_parameter_and_settings_version() -> None:
    dev = await make_user("DEVELOPER")
    hist_id, _log_id = await _seed(dev)
    async with open_session(DbContext.system(), job=True) as db:
        duplicate = ReputationLog(
            developer_id=dev, history_id=hist_id, parameter="t", old=Decimal("0.5"),
            new=Decimal("0.4"), raw_new=Decimal("0.4"), reason_code="ON_TIME",
            formula_version=1, settings_version=5,
        )  # fmt: skip
        db.add(duplicate)
        with pytest.raises(DbErrors):
            await db.flush()


@pytest.mark.parametrize(
    "changes",
    [
        {"gamma_comm": Decimal("1.5")},
        {"internal_slots": [Decimal("0.5"), Decimal("1.2")]},
        {"deadline_days": 0},
        {"t_days": -1},
        {"project_label": ""},
        {"sim_version": None},  # a SIMULATED row must say which simulator made it
    ],
)
async def test_history_constraints_refuse_bad_rows(changes: dict[str, Any]) -> None:
    dev = await make_user("DEVELOPER")
    async with open_session(DbContext.system(), job=True) as db:
        row = _history(dev)
        for key, value in changes.items():
            setattr(row, key, value)
        db.add(row)
        with pytest.raises(DbErrors):
            await db.flush()


async def test_log_refuses_unknown_parameters_and_out_of_range_values() -> None:
    dev = await make_user("DEVELOPER")
    hist_id, _ = await _seed(dev)
    for parameter, new in (("zeta", Decimal("0.5")), ("x", Decimal("1.5"))):
        async with open_session(DbContext.system(), job=True) as db:
            db.add(ReputationLog(developer_id=dev, history_id=hist_id, parameter=parameter,
                                 old=Decimal("0.5"), new=new, raw_new=new, reason_code="X",
                                 formula_version=1, settings_version=99))  # fmt: skip
            with pytest.raises(DbErrors):
                await db.flush()
