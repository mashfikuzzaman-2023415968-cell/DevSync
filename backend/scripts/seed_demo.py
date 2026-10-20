"""Demo seed (`make seed-demo STAGE=N`, spec §18.1/§18.4).

STAGE=1 (Demo 1, after Phase 5) loads the "Online ordering system" project in BIDDING with the
documented 12 sealed bids — 10 eligible, Shakib `TOO_SLOW`, Lamia `NO_SKILL_EVIDENCE` — plus the
client (payment verified), 9 experienced developers with fixed reputation snapshots (§18.4) and
3 newcomers with skill evidence. The script then runs Algorithm 1 over the seeded bids and
asserts the documented eligible/ineligible counts, so the data can't drift (the gate relies on
this). Run inside the worker container: `make seed-demo STAGE=1`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.filtering import ReasonCode
from app.core.clock import get_clock
from app.core.config import Settings, get_settings
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.bidding import Bid, BidStatus
from app.models.identity import User
from app.models.profiles import (
    DeveloperProfile,
    DeveloperSkill,
    EvidenceSource,
    Skill,
    SkillEvidence,
)
from app.models.projects import Milestone, MilestoneDependency, Project, ProjectSlot, ProjectStatus
from app.models.reputation import ReputationSnapshot
from app.services import bids as bids_svc
from app.services.testing.seed import create_user

_PW = "demo password strong 1!"

SEED_DIR = Path(__file__).resolve().parent / "seed_data"

# Experienced developers (fixed snapshots) → display name.
EXPERIENCED = {
    "arif": "Arif Hossain",
    "nusrat": "Nusrat Jahan",
    "tanvir": "Tanvir Ahmed",
    "sadia": "Sadia Islam",
    "rafi": "Rafi Karim",
    "imran": "Imran Kabir",
    "farhan": "Farhan Siddique",
    "shakib": "Shakib Hasan",
    "zahid": "Zahid Mahmud",
}
# Newcomers → (display name, evidence skill, evidence score).
NEWCOMERS = {
    "nadia": ("Nadia Rahman", "React", Decimal("0.85")),
    "mehjabin": ("Mehjabin Chowdhury", "Testing", Decimal("0.90")),
    "lamia": ("Lamia Akter", "FastAPI", Decimal("0.75")),
}
SLOTS = ["React", "FastAPI", "PostgreSQL", "Testing"]
# (slug, slot skill, days, price_paisa, declared skills). The one ACTIVE bid per developer.
BIDS = [
    ("nadia", "React", 20, 1_800_000, ["React"]),
    ("arif", "React", 18, 2_600_000, ["React"]),
    ("nusrat", "React", 22, 2_400_000, ["React"]),
    ("tanvir", "FastAPI", 20, 2_800_000, ["FastAPI"]),
    ("farhan", "FastAPI", 19, 2_500_000, ["FastAPI"]),
    ("sadia", "PostgreSQL", 21, 2_300_000, ["PostgreSQL"]),
    ("rafi", "PostgreSQL", 20, 2_200_000, ["PostgreSQL"]),
    # Lamia lists PostgreSQL but only has FastAPI evidence → NO_SKILL_EVIDENCE (newcomer rule).
    ("lamia", "PostgreSQL", 20, 1_900_000, ["PostgreSQL", "FastAPI"]),
    ("mehjabin", "Testing", 20, 1_700_000, ["Testing"]),
    ("zahid", "Testing", 22, 1_900_000, ["Testing"]),
    ("imran", "Testing", 19, 2_000_000, ["Testing"]),
    # Shakib needs 31 days > the 30-day deadline → TOO_SLOW.
    ("shakib", "Testing", 31, 1_800_000, ["Testing"]),
]
# §18.2 milestones (name, days, share_bp, predecessor indices).
MILESTONES = [
    ("Requirements & design", 4, 1000, []),
    ("Database", 5, 1500, [0]),
    ("Backend API", 8, 3000, [1]),
    ("Frontend", 9, 2500, [0]),
    ("Integration", 3, 1000, [2, 3]),
    ("Testing & launch", 4, 1000, [4]),
]

_F = Decimal("0.7")
_G = (Decimal("0.5"), Decimal("0.25"), Decimal("0.25"))


def _as(uid: uuid.UUID, role: str) -> AbstractAsyncContextManager[AsyncSession]:
    return open_session(DbContext(user_id=uid, role=role))


async def _skill_ids(db: AsyncSession) -> dict[str, uuid.UUID]:
    rows = await db.scalars(select(Skill).where(Skill.name.in_([*SLOTS, "FastAPI"])))
    return {s.name: s.id for s in rows}


async def _make_users(settings: Settings) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    people = {**EXPERIENCED, **{k: v[0] for k, v in NEWCOMERS.items()}}
    for i, (slug, name) in enumerate(people.items(), start=1):
        res = await create_user(
            settings,
            role="DEVELOPER",
            email=f"{slug}@devsync.local",
            phone=f"+88017{10000000 + i}",
            password=_PW,
            display_name=name,
            verified=True,
            with_totp=False,
        )
        ids[slug] = uuid.UUID(res["user_id"])
    res = await create_user(
        settings,
        role="CLIENT",
        email="rahim@devsync.local",
        phone="+8801799999999",
        password=_PW,
        display_name="Rahim (Rahim's Kitchen)",
        verified=True,
        with_totp=False,
    )
    ids["rahim"] = uuid.UUID(res["user_id"])
    return ids


async def _seed_reputation(ids: dict[str, uuid.UUID]) -> None:
    data = json.loads((SEED_DIR / "stage1_reputation.json").read_text())
    async with open_session(DbContext.system(), job=True) as db:
        for slug in EXPERIENCED:
            r = data[slug]
            omega, x, beta, mu, t = (Decimal(str(r[k])) for k in ("omega", "x", "beta", "mu", "t"))
            c = _F * omega + (Decimal(1) - _F) * x
            p = _G[0] * beta + _G[1] * mu + _G[2] * t
            db.add(
                ReputationSnapshot(
                    developer_id=ids[slug],
                    omega=omega,
                    x=x,
                    xm=Decimal(str(r["xm"])),
                    beta=beta,
                    mu=mu,
                    t=t,
                    c=c.quantize(Decimal("0.001")),
                    p=p.quantize(Decimal("0.001")),
                    completed_projects=r["completed_projects"],
                    distinct_clients=r["distinct_clients"],
                )
            )
        await db.commit()


async def _seed_dev_data(ids: dict[str, uuid.UUID], skills: dict[str, uuid.UUID]) -> None:
    declared: dict[str, set[str]] = {}
    for slug, _slot, _days, _price, dev_skills in BIDS:
        declared[slug] = set(dev_skills)
    now = get_clock().now()
    for slug, skill_names in declared.items():
        # A developer declares their own skills (RLS owner policy).
        async with _as(ids[slug], "DEVELOPER") as db:
            db.add(
                DeveloperProfile(user_id=ids[slug], headline="Seeded developer", hours_per_week=40)
            )
            for name in skill_names:
                db.add(DeveloperSkill(user_id=ids[slug], skill_id=skills[name], self_level=4))
            await db.commit()
    # Newcomer skill evidence is written as SYSTEM, like the skill-test scoring definer (§9.1).
    async with open_session(DbContext.system(), job=True) as db:
        for slug, (_name, skill, score) in NEWCOMERS.items():
            db.add(
                SkillEvidence(
                    user_id=ids[slug],
                    skill_id=skills[skill],
                    source=EvidenceSource.TEST,
                    score=score,
                    at=now,
                )
            )
        await db.commit()


async def _seed_project(
    ids: dict[str, uuid.UUID], skills: dict[str, uuid.UUID]
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    rahim = ids["rahim"]
    # Mark the client's payment method verified (own-row update under RLS).
    async with _as(rahim, "CLIENT") as db:
        user = await db.get(User, rahim)
        if user is None:
            raise SystemExit("client row missing after create_user")
        user.payment_verified_at = get_clock().now()
        await db.commit()
    slot_ids: dict[str, uuid.UUID] = {}
    async with _as(rahim, "CLIENT") as db:
        project = Project(
            client_id=rahim,
            title="Online ordering system",
            summary="A web app for a restaurant to take and track orders.",
            requirements="React front end, FastAPI back end, PostgreSQL, tested.",
            budget_paisa=12_000_000,
            deadline_days=30,
            team_size=4,
            status=ProjectStatus.BIDDING,
            start_date=get_clock().now().date() + timedelta(days=3),
            bidding_deadline=datetime.now(UTC) + timedelta(days=7),
        )
        db.add(project)
        await db.flush()
        for name in SLOTS:
            slot = ProjectSlot(
                project_id=project.id, skill_id=skills[name], label=f"{name} developer", count=1
            )
            db.add(slot)
            await db.flush()
            slot_ids[name] = slot.id
        milestones: list[Milestone] = []
        for pos, (mname, days, share, _preds) in enumerate(MILESTONES):
            m = Milestone(
                project_id=project.id, name=mname, duration_days=days, share_bp=share, position=pos
            )
            db.add(m)
            await db.flush()
            milestones.append(m)
        for pos, (_mname, _days, _share, preds) in enumerate(MILESTONES):
            for pre in preds:
                db.add(
                    MilestoneDependency(
                        project_id=project.id,
                        predecessor_id=milestones[pre].id,
                        successor_id=milestones[pos].id,
                    )
                )
        pid = project.id
        await db.commit()
    return pid, slot_ids


async def _seed_bids(
    ids: dict[str, uuid.UUID], pid: uuid.UUID, slot_ids: dict[str, uuid.UUID]
) -> None:
    for slug, slot_name, days, price, _skills in BIDS:
        async with _as(ids[slug], "DEVELOPER") as db:
            db.add(
                Bid(
                    project_id=pid,
                    developer_id=ids[slug],
                    slot_id=slot_ids[slot_name],
                    price_paisa=price,
                    days_needed=days,
                    hours_per_week_committed=20,
                    status=BidStatus.ACTIVE,
                )
            )
            await db.commit()


async def _assert_filter(pid: uuid.UUID) -> None:
    """Run Algorithm 1 over the seeded bids and assert the documented counts (§18.4)."""
    async with open_session(DbContext.system(), job=True) as db:
        settings = await active_settings(db)
        project = await db.get(Project, pid)
        if project is None:
            raise SystemExit("seeded project missing")
        _bids, result, _reps = await bids_svc.evaluate_project(
            db, project, settings, get_clock().now().date()
        )
    rejected = dict(result.rejected)
    reasons = sorted(r.value for r in rejected.values())
    eligible = len(result.eligible)
    print(f"seed-demo STAGE=1: {eligible} eligible, {len(rejected)} ineligible {reasons}")
    expected = sorted([ReasonCode.TOO_SLOW.value, ReasonCode.NO_SKILL_EVIDENCE.value])
    if eligible != 10 or reasons != expected or result.too_few:
        raise SystemExit(
            f"seed assertion failed: eligible={eligible} (want 10), reasons={reasons} "
            f"(want {expected}), too_few={result.too_few}"
        )


async def _seed_too_few(ids: dict[str, uuid.UUID], skills: dict[str, uuid.UUID]) -> None:
    """A second BIDDING project with far too few bids, for the too-few-bids banner (§9.19)."""
    rahim = ids["rahim"]
    async with _as(rahim, "CLIENT") as db:
        project = Project(
            client_id=rahim,
            title="Mobile companion app",
            summary="A mobile companion for the ordering system.",
            requirements="React Native screens and an API client.",
            budget_paisa=8_000_000,
            deadline_days=25,
            team_size=3,
            status=ProjectStatus.BIDDING,
            start_date=get_clock().now().date() + timedelta(days=5),
            bidding_deadline=datetime.now(UTC) + timedelta(days=7),
        )
        db.add(project)
        await db.flush()
        slot = ProjectSlot(
            project_id=project.id, skill_id=skills["React"], label="React developer", count=3
        )
        db.add(slot)
        await db.flush()
        m = Milestone(
            project_id=project.id, name="Build", duration_days=20, share_bp=10_000, position=0
        )
        db.add(m)
        pid, sid = project.id, slot.id
        await db.commit()
    # A single eligible bid, far short of the team of three.
    async with _as(ids["arif"], "DEVELOPER") as db:
        db.add(
            Bid(
                project_id=pid,
                developer_id=ids["arif"],
                slot_id=sid,
                price_paisa=2_500_000,
                days_needed=18,
                hours_per_week_committed=20,
                status=BidStatus.ACTIVE,
            )
        )
        await db.commit()


async def _make_admin(settings: Settings) -> dict[str, str]:
    res = await create_user(
        settings,
        role="ADMIN",
        email="admin@devsync.local",
        phone=None,
        password=_PW,
        display_name="Administrator",
        verified=True,
        with_totp=True,
    )
    return {"totp_secret": res["totp_secret"] or ""}


def _print_accounts(admin: dict[str, str]) -> None:
    """Print the demo accounts once (the Makefile tees this to runs/demos/accounts-1.txt)."""
    print("=== DEMO ACCOUNTS (STAGE 1) ===")
    print(f"client       rahim@devsync.local            {_PW}")
    for slug in EXPERIENCED:
        print(f"developer    {slug}@devsync.local{' ' * (18 - len(slug))}{_PW}")
    for slug in NEWCOMERS:
        print(f"newcomer     {slug}@devsync.local{' ' * (18 - len(slug))}{_PW}")
    print(
        f"admin        admin@devsync.local            {_PW}   TOTP secret: {admin['totp_secret']}"
    )
    print("=== END DEMO ACCOUNTS ===")


async def seed_stage1() -> None:
    settings = get_settings()
    async with open_session(DbContext.system(), job=True) as db:
        skills = await _skill_ids(db)
    missing = [s for s in SLOTS if s not in skills]
    if missing:
        raise SystemExit(f"skills not seeded: {missing}; run migrations first")
    ids = await _make_users(settings)
    admin = await _make_admin(settings)
    await _seed_reputation(ids)
    await _seed_dev_data(ids, skills)
    pid, slot_ids = await _seed_project(ids, skills)
    await _seed_bids(ids, pid, slot_ids)
    await _seed_too_few(ids, skills)
    await _assert_filter(pid)
    _print_accounts(admin)


def main() -> int:
    parser = argparse.ArgumentParser(description="DevSync demo seed")
    parser.add_argument("--stage", type=int, default=1)
    args = parser.parse_args()
    if args.stage != 1:
        raise SystemExit(f"stage {args.stage} is not available yet")
    asyncio.run(seed_stage1())
    return 0


if __name__ == "__main__":
    sys.exit(main())
