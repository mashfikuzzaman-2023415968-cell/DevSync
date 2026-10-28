"""Demo seed (`make seed-demo STAGE=N`, spec §18.1/§18.4).

STAGE=1 (Demo 1, after Phase 5) loads the "Online ordering system" project in BIDDING with the
documented 12 sealed bids — 10 eligible, Shakib `TOO_SLOW`, Lamia `NO_SKILL_EVIDENCE` — plus the
client (payment verified), 9 experienced developers with fixed reputation snapshots (§18.4) and
the newcomers (role assessment spec §14.1): Nadia and Mehjabin passed the role assessment for
their slot, Lamia failed hers, Rafsan has none (he takes it live in the demo), and Tahmid's attempt
ended under the two-leave rule (flagged, for the admin queue). Role results are real attempts,
taken through the same database functions as the app. Practice-test scores stay on profiles.
Every developer has a real profile (headline, bio, hours,
skills with levels, §18.1), the experienced ones portfolio items and verified test scores, and
Rahim his client profile (Rahim's Kitchen). A DRAFT project whose milestones depend on each other
in a loop shows cycle detection in the wizard, and a second BIDDING project has too few bids.
The script then runs Algorithm 1 over the seeded bids and asserts the documented
eligible/ineligible counts, so the data can't drift (the gate relies on this). Run inside the
worker container: `make seed-demo STAGE=1`.

Passwords are random per account and printed once (§18.1); `make demo-reset` saves the output to
`runs/demos/accounts-N.txt` (gitignored, owner-only). For rehearsals, `DEMO_PASSWORD` (12+
characters) gives every demo account that one password.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
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
    ClientProfile,
    DeveloperProfile,
    DeveloperSkill,
    EvidenceSource,
    PortfolioItem,
    Skill,
    SkillEvidence,
)
from app.models.projects import Milestone, MilestoneDependency, Project, ProjectSlot, ProjectStatus
from app.models.reputation import ReputationSnapshot
from app.services import bids as bids_svc
from app.services import role_assessments
from app.services.testing import role_attempts
from app.services.testing.seed import create_user

MIN_FIXED_PASSWORD = 12

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
# Newcomers → (display name, practice-test skill, practice score or None).
NEWCOMERS: dict[str, tuple[str, str, Decimal | None]] = {
    "nadia": ("Nadia Rahman", "React", Decimal("0.85")),
    "mehjabin": ("Mehjabin Chowdhury", "Testing", Decimal("0.90")),
    "lamia": ("Lamia Akter", "FastAPI", Decimal("0.75")),
    "rafsan": ("Rafsan Haque", "React", None),
    "tahmid": ("Tahmid Rahman", "React", None),
}
# Role assessments taken for a slot of the ordering system (role assessment spec §14.1):
# slug → (slot skill, outcome). Real attempts: "pass" answers all but two questions right,
# "fail" every other one, "ended" leaves the page twice after three answers.
ROLE_RESULTS: dict[str, tuple[str, str]] = {
    "nadia": ("React", "pass"),
    "mehjabin": ("Testing", "pass"),
    "lamia": ("FastAPI", "fail"),
    "tahmid": ("React", "ended"),
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
    # Lamia failed the FastAPI role assessment → NO_SKILL_EVIDENCE (newcomer rule).
    ("lamia", "FastAPI", 20, 1_900_000, ["FastAPI", "PostgreSQL"]),
    ("mehjabin", "Testing", 20, 1_700_000, ["Testing"]),
    ("zahid", "Testing", 22, 1_900_000, ["Testing"]),
    ("imran", "Testing", 19, 2_000_000, ["Testing"]),
    # Shakib needs 31 days > the 30-day deadline → TOO_SLOW.
    ("shakib", "Testing", 31, 1_800_000, ["Testing"]),
]
# §18.1 profiles: slug → (headline, bio, hours a week, {skill: self level 1–5}). Every bid
# commits 20 hours a week, so nobody has fewer free hours than that.
PROFILES: dict[str, tuple[str, str, int, dict[str, int]]] = {
    "arif": ("Full-stack developer: React, FastAPI and PostgreSQL",
             "Eight shipped projects for five clients, from clinic booking to pharmacy stock. "
             "I like small teams, clear milestones and weekly demos.",
             40, {"React": 5, "FastAPI": 4, "PostgreSQL": 4}),
    "nusrat": ("React developer focused on fast, accessible interfaces",
               "Six projects of front-end work: booking flows, dashboards and forms that work "
               "with a screen reader. I write the component tests too.",
               35, {"React": 5, "UI/UX": 4, "Testing": 3}),
    "tanvir": ("Backend developer: FastAPI services and clean APIs",
               "Typed REST APIs with FastAPI and PostgreSQL, with tests and docs from day one. "
               "Four projects so far, mostly logistics.",
               30, {"FastAPI": 4, "PostgreSQL": 3, "DevOps": 3}),
    "sadia": ("Database engineer: PostgreSQL schemas, reports and tuning",
              "Schemas that stay fast as the data grows: indexing, migrations and reporting "
              "queries. Three projects for schools and retailers.",
              30, {"PostgreSQL": 5, "FastAPI": 3}),
    "rafi": ("PostgreSQL developer and data pipelines",
             "Data modelling, imports and nightly reports in PostgreSQL, with some Docker and CI "
             "work on the side.",
             25, {"PostgreSQL": 4, "DevOps": 3}),
    "imran": ("QA engineer: automated and manual testing",
              "Seven testing projects, all for one long-term client in microfinance: test plans, "
              "regression suites and release checks.",
              30, {"Testing": 4, "React": 2}),
    "farhan": ("Python developer: FastAPI and payment integrations",
               "APIs and third-party integrations (payments, SMS, maps) in FastAPI. Three "
               "projects for three clients.",
               30, {"FastAPI": 4, "Node.js": 3}),
    "shakib": ("Tester for web and mobile apps",
               "Web and Flutter app testing with written test plans. Four projects; working on "
               "my delivery times.",
               25, {"Testing": 4, "Flutter": 3}),
    "zahid": ("QA and test automation",
              "Two projects of end-to-end testing with Playwright, keen to take on more.",
              20, {"Testing": 3}),
    "nadia": ("Front-end developer: React, new to DevSync",
              "Recent graduate building React apps; React practice test 85%.",
              30, {"React": 4, "UI/UX": 3}),
    "mehjabin": ("QA tester: test plans and automation",
                 "Careful tester new to DevSync; Testing practice test 90%.",
                 25, {"Testing": 4}),
    "lamia": ("Backend developer learning databases",
              "FastAPI developer new to DevSync (FastAPI practice test 75%), growing into "
              "PostgreSQL.",
              30, {"FastAPI": 3, "PostgreSQL": 2}),
    "rafsan": ("Junior React developer",
               "Final-year student who builds React side projects; looking for a first "
               "paid team project.",
               25, {"React": 3}),
    "tahmid": ("React developer, new to DevSync",
               "Self-taught React developer working on his first freelance projects.",
               25, {"React": 3}),
}  # fmt: skip
# Verified test scores of the experienced developers (the newcomers' are in NEWCOMERS). Filtering
# reads only the newcomers' evidence; experienced developers pass on their fixed snapshots.
EXPERIENCED_EVIDENCE: dict[str, dict[str, Decimal]] = {
    "arif": {"React": Decimal("0.90"), "FastAPI": Decimal("0.80")},
    "nusrat": {"React": Decimal("0.95")},
    "tanvir": {"FastAPI": Decimal("0.80")},
    "sadia": {"PostgreSQL": Decimal("0.85")},
    "rafi": {"PostgreSQL": Decimal("0.75")},
    "imran": {"Testing": Decimal("0.80")},
    "farhan": {"FastAPI": Decimal("0.70")},
    "shakib": {"Testing": Decimal("0.70")},
    "zahid": {"Testing": Decimal("0.70")},
}
# Portfolio items of the experienced developers: slug → [(title, description, skills)]. No links
# or images, so the offline demo never reaches out.
PORTFOLIO: dict[str, list[tuple[str, str, list[str]]]] = {
    "arif": [
        ("Pharmacy stock and orders", "Stock levels, expiry alerts and supplier orders for a "
         "chain of four pharmacies.", ["React", "FastAPI", "PostgreSQL"]),
        ("Clinic booking app", "Patients book, move and cancel visits; staff see the day's "
         "queue.", ["React", "PostgreSQL"]),
    ],
    "nusrat": [
        ("Bus ticket booking", "Seat picker and checkout used on phones, keyboard and screen "
         "reader friendly.", ["React", "UI/UX"]),
        ("NGO donations dashboard", "Monthly donations and programme spending at a glance.",
         ["React"]),
    ],
    "tanvir": [("Courier tracking API", "Parcel events, rider assignment and delivery proofs.",
                ["FastAPI", "PostgreSQL"])],
    "sadia": [("School results database", "Results, transcripts and term reports for 2,000 "
               "students.", ["PostgreSQL"])],
    "rafi": [("Garment order reports", "Nightly imports and buyer reports for a garments "
              "exporter.", ["PostgreSQL"])],
    "imran": [("Microfinance app regression suite", "Release checks for loan and savings "
               "flows.", ["Testing"])],
    "farhan": [("Payment gateway integration", "Card and mobile-wallet payments with "
                "webhooks.", ["FastAPI"])],
    "shakib": [("Grocery app test plan", "Test plan and bug reports for a Flutter grocery app.",
                ["Testing", "Flutter"])],
    "zahid": [("Booking site end-to-end tests", "Playwright tests for a hotel booking site.",
               ["Testing"])],
}  # fmt: skip
# §18.2 milestones (name, days, share_bp, predecessor indices).
MILESTONES = [
    ("Requirements & design", 4, 1000, []),
    ("Database", 5, 1500, [0]),
    ("Backend API", 8, 3000, [1]),
    ("Frontend", 9, 2500, [0]),
    ("Integration", 3, 1000, [2, 3]),
    ("Testing & launch", 4, 1000, [4]),
]
# The DRAFT with a deliberate dependency loop (§18.4): Order queue → Kitchen screen → Ready
# alerts → Order queue. Reopened in the wizard, the Milestones step shows the loop and blocks
# "Continue" until one dependency is removed.
CYCLE_DRAFT = "Kitchen display system"
CYCLE_MILESTONES = [
    ("Requirements", 3, 1500, []),
    ("Order queue", 5, 2500, [0, 3]),
    ("Kitchen screen", 6, 3000, [1]),
    ("Ready alerts", 3, 2000, [2]),
    ("Launch", 2, 1000, [3]),
]
# Wizard step (1-based) of the Milestones step, for the cycle draft's direct link.
MILESTONES_STEP = 4


def demo_passwords(slugs: list[str], fixed: str | None) -> dict[str, str]:
    """One password per account: random (printed once) unless a rehearsal password is given."""
    fixed = (fixed or "").strip()
    if fixed and len(fixed) < MIN_FIXED_PASSWORD:
        raise SystemExit(f"DEMO_PASSWORD must be at least {MIN_FIXED_PASSWORD} characters")
    return {slug: fixed or secrets.token_urlsafe(12) for slug in slugs}


def check_seed_data() -> None:
    """Every bid's skills are listed on the bidder's profile (Lamia's PostgreSQL too: her
    ineligibility must stay NO_SKILL_EVIDENCE, not SKILL_MISMATCH); evidence and portfolio
    skills are ones the developer lists; shares add up; hours cover a bid's 20 a week."""
    for slug, slot, _days, _price, declared in BIDS:
        missing = {slot, *declared} - set(PROFILES[slug][3])
        if missing:
            raise SystemExit(f"seed data: {slug} bids on skills not on the profile: {missing}")
    for slug, scores in EXPERIENCED_EVIDENCE.items():
        if set(scores) - set(PROFILES[slug][3]):
            raise SystemExit(f"seed data: {slug} has evidence for an unlisted skill")
    for slug, items in PORTFOLIO.items():
        if any(set(skills) - set(PROFILES[slug][3]) for _t, _d, skills in items):
            raise SystemExit(f"seed data: {slug} has a portfolio item with an unlisted skill")
    if set(PROFILES) != set(EXPERIENCED) | set(NEWCOMERS):
        raise SystemExit("seed data: every developer needs exactly one profile")
    if any(hours < 20 for _h, _b, hours, _s in PROFILES.values()):
        raise SystemExit("seed data: every developer needs at least 20 free hours a week")
    for plan in (MILESTONES, CYCLE_MILESTONES):
        if sum(m[2] for m in plan) != 10_000:
            raise SystemExit("seed data: milestone shares must add up to 100%")


def _as(uid: uuid.UUID, role: str) -> AbstractAsyncContextManager[AsyncSession]:
    return open_session(DbContext(user_id=uid, role=role))


async def _skill_ids(db: AsyncSession) -> dict[str, uuid.UUID]:
    rows = await db.scalars(select(Skill))
    return {s.name: s.id for s in rows}


async def _make_users(settings: Settings, pw: dict[str, str]) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    people = {**EXPERIENCED, **{k: v[0] for k, v in NEWCOMERS.items()}}
    for i, (slug, name) in enumerate(people.items(), start=1):
        res = await create_user(
            settings,
            role="DEVELOPER",
            email=f"{slug}@devsync.local",
            phone=f"+88017{10000000 + i}",
            password=pw[slug],
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
        password=pw["rahim"],
        display_name="Rahim (Rahim's Kitchen)",
        verified=True,
        with_totp=False,
    )
    ids["rahim"] = uuid.UUID(res["user_id"])
    return ids


async def _seed_reputation(ids: dict[str, uuid.UUID]) -> None:
    data = json.loads((SEED_DIR / "stage1_reputation.json").read_text())
    async with open_session(DbContext.system(), job=True) as db:
        # C (Eq. 4) and P (Eq. 12) with the active `rep.f_default` / `rep.g` (§6.2).
        rep = (await active_settings(db)).rep
        f, (g1, g2, g3) = rep.f_default, rep.g
        for slug in EXPERIENCED:
            r = data[slug]
            omega, x, beta, mu, t = (Decimal(str(r[k])) for k in ("omega", "x", "beta", "mu", "t"))
            c = f * omega + (Decimal(1) - f) * x
            p = g1 * beta + g2 * mu + g3 * t
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
    """Profiles, listed skills and portfolios, written by each developer (RLS owner policies),
    then verified test scores."""
    for slug, (headline, bio, hours, levels) in PROFILES.items():
        async with _as(ids[slug], "DEVELOPER") as db:
            db.add(
                DeveloperProfile(
                    user_id=ids[slug], headline=headline, bio=bio, hours_per_week=hours
                )
            )
            for name, level in levels.items():
                db.add(DeveloperSkill(user_id=ids[slug], skill_id=skills[name], self_level=level))
            for pos, (title, description, item_skills) in enumerate(PORTFOLIO.get(slug, [])):
                db.add(
                    PortfolioItem(
                        user_id=ids[slug],
                        title=title,
                        description=description,
                        skill_ids=[skills[n] for n in item_skills],
                        position=pos,
                    )
                )
            await db.commit()
    # Test scores are written as SYSTEM, like the skill-test scoring definer (§9.1).
    now = get_clock().now()
    scores = {slug: dict(EXPERIENCED_EVIDENCE.get(slug, {})) for slug in PROFILES}
    for slug, (_name, skill, score) in NEWCOMERS.items():
        if score is not None:  # practice-test results (shown as practice, Decision 1)
            scores[slug][skill] = score
    async with open_session(DbContext.system(), job=True) as db:
        for slug, per_skill in scores.items():
            for skill, score in per_skill.items():
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


async def _seed_client_profile(rahim: uuid.UUID) -> None:
    """Rahim's organisation (§18.1), written by Rahim (RLS owner policy)."""
    async with _as(rahim, "CLIENT") as db:
        db.add(
            ClientProfile(
                user_id=rahim,
                organization="Rahim's Kitchen",
                description="A family restaurant in Dhanmondi, Dhaka, moving its phone orders "
                "online and planning a display for the kitchen.",
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
        await _add_plan(db, project.id, MILESTONES)
        pid = project.id
        await db.commit()
    return pid, slot_ids


async def _add_plan(
    db: AsyncSession, project_id: uuid.UUID, plan: list[tuple[str, int, int, list[int]]]
) -> None:
    """Milestones and their finish-to-start dependencies, straight into the tables."""
    milestones: list[Milestone] = []
    for pos, (mname, days, share, _preds) in enumerate(plan):
        m = Milestone(
            project_id=project_id, name=mname, duration_days=days, share_bp=share, position=pos
        )
        db.add(m)
        await db.flush()
        milestones.append(m)
    for pos, (_mname, _days, _share, preds) in enumerate(plan):
        for pre in preds:
            db.add(
                MilestoneDependency(
                    project_id=project_id,
                    predecessor_id=milestones[pre].id,
                    successor_id=milestones[pos].id,
                )
            )


async def _seed_cycle_draft(rahim: uuid.UUID, skills: dict[str, uuid.UUID]) -> uuid.UUID:
    """A DRAFT whose milestones form a loop, for showing cycle detection (§18.4). Written straight
    to the tables: the plan endpoints would (rightly) refuse to save the loop. No budget yet, so
    the draft is unfinished and can't be published."""
    async with _as(rahim, "CLIENT") as db:
        project = Project(
            client_id=rahim,
            title=CYCLE_DRAFT,
            summary="Orders appear on a kitchen screen and staff mark them ready.",
            requirements="A screen in the kitchen, alerts at the counter, keeps working offline.",
            budget_paisa=0,
            deadline_days=20,
            team_size=2,
            status=ProjectStatus.DRAFT,
        )
        db.add(project)
        await db.flush()
        for name in ("React", "FastAPI"):
            db.add(
                ProjectSlot(
                    project_id=project.id, skill_id=skills[name], label=f"{name} developer", count=1
                )
            )
        await _add_plan(db, project.id, CYCLE_MILESTONES)
        pid = project.id
        await db.commit()
    return pid


async def _seed_role_results(
    ids: dict[str, uuid.UUID], pid: uuid.UUID, slot_ids: dict[str, uuid.UUID]
) -> dict[str, uuid.UUID]:
    """Real role attempts (§14.1); returns each passer's evidence id for their bid."""
    plans = {
        "pass": {"plan": role_attempts.wrong_on(2, 9)},
        "fail": {"plan": role_attempts.every_other},
        "ended": {"stop_after": 3, "leaves": 2},
    }
    evidence: dict[str, uuid.UUID] = {}
    for n, (slug, (skill, outcome)) in enumerate(ROLE_RESULTS.items(), start=1):
        taken = await role_attempts.take(
            ids[slug], pid, slot_ids[skill], seed=1000 + n, **plans[outcome]  # type: ignore[arg-type]
        )
        if (outcome == "pass") != bool(taken.passed):
            raise SystemExit(f"seed assertion failed: {slug}'s role assessment should {outcome}")
        if outcome == "pass" and taken.evidence_id is not None:
            evidence[slug] = taken.evidence_id
    return evidence


async def _seed_bids(
    ids: dict[str, uuid.UUID],
    pid: uuid.UUID,
    slot_ids: dict[str, uuid.UUID],
    evidence: dict[str, uuid.UUID],
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
                    assessment_evidence_id=evidence.get(slug),
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


async def _make_admin(settings: Settings, password: str) -> dict[str, str]:
    res = await create_user(
        settings,
        role="ADMIN",
        email="admin@devsync.local",
        phone=None,
        password=password,
        display_name="Administrator",
        verified=True,
        with_totp=True,
    )
    return {"totp_secret": res["totp_secret"] or ""}


def _print_accounts(
    admin: dict[str, str], pw: dict[str, str], origin: str, cycle_id: uuid.UUID
) -> None:
    """Print the demo accounts once (`make demo-reset` saves this to runs/demos/accounts-1.txt).
    `make demo-preflight` reads the `client` line: role, email, password."""
    print("=== DEMO ACCOUNTS (STAGE 1) ===")
    print(f"client       rahim@devsync.local            {pw['rahim']}")
    for slug in EXPERIENCED:
        print(f"developer    {slug}@devsync.local{' ' * (18 - len(slug))}{pw[slug]}")
    for slug in NEWCOMERS:
        print(f"newcomer     {slug}@devsync.local{' ' * (18 - len(slug))}{pw[slug]}")
    print(
        f"admin        admin@devsync.local            {pw['admin']}   "
        f"TOTP secret: {admin['totp_secret']}"
    )
    print("=== END DEMO ACCOUNTS ===")
    print(
        f"cycle draft  {origin}/client/projects/new?draft={cycle_id}&step={MILESTONES_STEP}"
        f"  (as Rahim: '{CYCLE_DRAFT}', milestones in a loop)"
    )
    print("codes        texts and emails arrive in Mailpit: http://127.0.0.1:8025")


async def seed_stage1() -> None:
    check_seed_data()
    settings = get_settings()
    async with open_session(DbContext.system(), job=True) as db:
        skills = await _skill_ids(db)
    needed = {n for p in PROFILES.values() for n in p[3]} | set(SLOTS)
    missing = sorted(needed - set(skills))
    if missing:
        raise SystemExit(f"skills not seeded: {missing}; run migrations first")
    pw = demo_passwords([*PROFILES, "rahim", "admin"], os.environ.get("DEMO_PASSWORD"))
    ids = await _make_users(settings, pw)
    admin = await _make_admin(settings, pw["admin"])
    await _seed_reputation(ids)
    await _seed_dev_data(ids, skills)
    await _seed_client_profile(ids["rahim"])
    pid, slot_ids = await _seed_project(ids, skills)
    await role_assessments.ensure_links_as_system(pid)  # blueprints, as at publish (§4.4)
    evidence = await _seed_role_results(ids, pid, slot_ids)
    await _seed_bids(ids, pid, slot_ids, evidence)
    await _seed_too_few(ids, skills)
    cycle_id = await _seed_cycle_draft(ids["rahim"], skills)
    await _assert_filter(pid)
    _print_accounts(admin, pw, settings.PUBLIC_ORIGIN.rstrip("/"), cycle_id)


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
