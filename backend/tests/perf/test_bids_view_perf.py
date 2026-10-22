"""Performance budgets for Algorithm 1 at marketplace scale (spec §16, Phase 5 follow-up D54).

- the pure filter over 200 bids stays well under the PSO budget it feeds;
- evaluating a project with 200 active bids against the real database (reputations, skills,
  evidence, hours, reservations for every bidder) uses a fixed number of queries — not one per
  bid — and finishes inside the budget.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, insert, select

from app.algorithms.filtering import BidInput, FilterParams, ProjectInput, SlotSpec, filter_bids
from app.core.config import Environment
from app.core.security import hash_password
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import get_job_engine, open_session
from app.models import User, UserRole, UserStatus
from app.models.bidding import Bid, BidStatus
from app.models.profiles import DeveloperSkill, Skill
from app.models.projects import Project, ProjectSlot, ProjectStatus
from app.models.reputation import ReputationSnapshot
from app.services import bids as bids_svc
from tests.helpers import stack_available, unique_email, unique_phone

pytestmark = [pytest.mark.perf]

BIDS = 200
FILTER_BUDGET_S = 0.05
EVALUATE_BUDGET_S = 2.0
QUERY_BUDGET = 25  # independent of the number of bids


def test_filter_200_bids_within_budget() -> None:
    project = ProjectInput(30, 11_400_000, {f"s{i}": SlotSpec(f"k{i}", 2) for i in range(4)})
    bids = [
        BidInput(
            bid_id=f"b{i}",
            slot_id=f"s{i % 4}",
            skill_id=f"k{i % 4}",
            developer_id=f"d{i}",
            is_newcomer=i % 5 == 0,
            p=(i % 10) / 10,
            c=((i * 7) % 10) / 10,
            t_days=10 + i % 30,
            c_paisa=500_000 + (i * 37_000) % 3_000_000,
            skill_evidence_score=0.7 if i % 3 else None,
            has_slot_skill=True,
            active=True,
            available=i % 11 != 0,
            self_dealing=False,
        )
        for i in range(BIDS)
    ]
    start = time.perf_counter()
    for _ in range(10):
        filter_bids(bids, project, FilterParams(team_size=8))
    assert (time.perf_counter() - start) / 10 < FILTER_BUDGET_S


@pytest.mark.integration
async def test_evaluating_200_bids_uses_a_fixed_number_of_queries(
    monkeypatch: pytest.MonkeyPatch, migrated: str, migration_url: str
) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)
    # Bulk setup as the migrator (it owns the tables), so the test measures evaluation only.
    password_hash = hash_password("perf test password 1!")  # one hash for every account
    client_id, project_id, slot_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    dev_ids = [uuid.uuid4() for _ in range(BIDS)]

    def user(uid: uuid.UUID, role: UserRole, name: str) -> dict[str, object]:
        return {
            "id": uid,
            "email": unique_email(name),
            "phone_e164": unique_phone(),
            "role": role,
            "status": UserStatus.ACTIVE,
            "display_name": name,
            "password_hash": password_hash,
        }

    engine = create_engine(migration_url)
    try:
        with engine.begin() as conn:
            skill_id = conn.execute(select(Skill.id).order_by(Skill.name).limit(1)).scalar_one()
            conn.execute(
                insert(User.__table__),
                [user(client_id, UserRole.CLIENT, "perf-client")]
                + [user(d, UserRole.DEVELOPER, f"perf-dev{i}") for i, d in enumerate(dev_ids)],
            )
            conn.execute(
                insert(Project.__table__).values(
                    id=project_id,
                    client_id=client_id,
                    title="Perf ordering project",
                    budget_paisa=50_000_000,
                    deadline_days=30,
                    team_size=4,
                    status=ProjectStatus.BIDDING,
                    bidding_deadline=datetime.now(UTC) + timedelta(days=3),
                )
            )
            conn.execute(
                insert(ProjectSlot.__table__).values(
                    id=slot_id, project_id=project_id, skill_id=skill_id, count=4, label="Perf"
                )
            )
            conn.execute(
                insert(DeveloperSkill.__table__),
                [{"user_id": d, "skill_id": skill_id, "self_level": 3} for d in dev_ids],
            )
            conn.execute(
                insert(ReputationSnapshot.__table__),
                [
                    {
                        "developer_id": d,
                        "omega": Decimal("0.6"),
                        "x": Decimal("0.7"),
                        "xm": Decimal("0.6"),
                        "beta": Decimal("0.8"),
                        "mu": Decimal("0.7"),
                        "t": Decimal("0.8"),
                        "c": Decimal(f"{0.3 + (i % 7) / 10:.3f}"),
                        "p": Decimal(f"{0.3 + (i % 6) / 10:.3f}"),
                        "completed_projects": 5,
                        "distinct_clients": 3,
                    }
                    for i, d in enumerate(dev_ids)
                ],
            )
            conn.execute(
                insert(Bid.__table__),
                [
                    {
                        "project_id": project_id,
                        "developer_id": d,
                        "slot_id": slot_id,
                        "price_paisa": 1_000_000 + i * 10_000,
                        "days_needed": 10 + i % 25,
                        "hours_per_week_committed": 20,
                        "status": BidStatus.ACTIVE,
                    }
                    for i, d in enumerate(dev_ids)
                ],
            )
    finally:
        engine.dispose()

    queries = 0

    def count(*_args: object) -> None:
        nonlocal queries
        queries += 1

    engine = get_job_engine().sync_engine
    async with open_session(DbContext.system(), job=True) as db:
        settings = await active_settings(db)
        loaded = await db.get(Project, project_id)
        assert loaded is not None
        event.listen(engine, "before_cursor_execute", count)
        try:
            start = time.perf_counter()
            ev = await bids_svc.evaluate(db, loaded, settings, datetime.now(UTC).date())
            elapsed = time.perf_counter() - start
        finally:
            event.remove(engine, "before_cursor_execute", count)
    assert len(ev.bids) == BIDS
    assert len(ev.result.eligible) + len(ev.result.rejected) == BIDS
    assert queries <= QUERY_BUDGET, f"{queries} queries for {BIDS} bids"
    assert elapsed < EVALUATE_BUDGET_S, f"{elapsed:.2f}s"
