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

STAGE=2 (Phase 6 part of the Demo 2 seed, §18.4; DECISIONS D93) loads the same people and
projects, but the experienced developers' reputations are **computed** by the Phase 6 engine from
simulated project histories instead of the fixed stage-1 table: the market simulator generates
each persona's completed projects (`seed_data/stage2_personas.json`, fixed seed), the histories
are stored as SIMULATED `reputation_history` rows, and `reputation.recalculate_all` scores them.
The script asserts the computed values against `scripts/seed_data/stage2_reputation_golden.json`
(so a change can't drift silently; `--write-golden` rewrites it after a deliberate change) and
that the ordering project still gives the documented 10 eligible bids; then it closes that
project's bidding through the deadline job, so it is FORMING and ready for team formation
(Phase 7, D116). The rest of the Demo 2 seed
(in-progress, completed and disputed projects) arrives with Phases 8–12.

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
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms import weeks
from app.algorithms.filtering import ReasonCode
from app.algorithms.simulator import Market, Persona, SimParams, simulate_market
from app.algorithms.weeks import DHAKA
from app.core.authz import Principal
from app.core.clock import get_clock
from app.core.config import Settings, get_settings
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.jobs import bidding_jobs
from app.models.bidding import Bid, BidStatus
from app.models.formation import (
    FormationRun,
    Invitation,
    MemberStatus,
    RepairProposal,
    Team,
    TeamMember,
)
from app.models.identity import User
from app.models.profiles import (
    ClientProfile,
    DeveloperProfile,
    DeveloperSkill,
    EvidenceSource,
    PortfolioItem,
    Skill,
    SkillDomain,
    SkillEvidence,
)
from app.models.projects import (
    Milestone,
    MilestoneDependency,
    MilestoneSkill,
    MilestoneStatus,
    Project,
    ProjectSlot,
    ProjectStatus,
)
from app.models.reputation import ReputationHistory, ReputationSnapshot, ReputationSource
from app.models.workspace import CommentTarget, ForecastSnapshot, Risk, RiskStatus
from app.schemas.checkins import CheckinCreate
from app.schemas.comments import CommentCreate
from app.schemas.formation import FormationRunCreate
from app.schemas.tasks import TaskCreate, TaskMove
from app.schemas.team import ChooseLeadIn, DeclineIn
from app.services import bids as bids_svc
from app.services import checkins as checkins_svc
from app.services import comments as comments_svc
from app.services import formation as formation_svc
from app.services import (
    formation_runner,
    monitoring,
    platform_settings,
    reputation_engine,
    role_assessments,
)
from app.services import tasks as tasks_svc
from app.services import team as team_svc
from app.services.context import Ctx
from app.services.testing import role_attempts
from app.services.testing.seed import create_user

MIN_FIXED_PASSWORD = 12

SEED_DIR = Path(__file__).resolve().parent / "seed_data"
STAGE2_FILE = SEED_DIR / "stage2_personas.json"
# With the other seed data (D139): the production image used by `make demo-up` has no `tests/`.
GOLDEN_FILE = SEED_DIR / "stage2_reputation_golden.json"
# Simulated projects finish one every 40 days from this date (fixed, so the seed is reproducible).
HISTORY_START = datetime(2024, 7, 1, 12, tzinfo=UTC)
HISTORY_SPACING = timedelta(days=40)
# Readable names for simulated projects, by domain (the UI labels them "Simulated").
PROJECT_NAMES: dict[str, tuple[str, ...]] = {
    "FRONTEND": ("Clinic booking site", "Bakery ordering page", "Tutor finder", "Event tickets"),
    "BACKEND": ("Courier tracking API", "Pharmacy stock API", "Payroll service", "School fees API"),
    "DATABASE": ("Library catalogue", "Retail sales reports", "Hospital records", "Hostel ledger"),
    "MOBILE": ("Bus pass app", "Grocery delivery app", "Field survey app", "Fitness tracker"),
    "DESIGN": ("NGO website redesign", "Food app UI kit", "Bank onboarding flow", "Shop branding"),
    "TESTING": ("Microfinance regression suite", "E-commerce release checks", "Clinic app QA",
                "Telecom portal tests"),
    "DEVOPS": ("CI pipeline setup", "Cloud migration", "Monitoring stack", "Backup automation"),
    "DATA": ("Sales dashboard", "Crop yield analysis", "Survey data cleanup", "Footfall report"),
}  # fmt: skip

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
# A second client and more open projects, so Find Projects, the filters and a guest's public list
# have something to browse. They are real BIDDING projects with plans and no bids; only the
# "Online ordering system" carries the documented bids.
FARZANA = "farzana"
# (owner slug, title, summary, requirements, budget_paisa, deadline_days, bidding days left,
#  start in days, slots [skill, count], milestones [(name, days, share_bp, predecessors)]).
MARKET_PROJECTS: list[
    tuple[
        str,
        str,
        str,
        str,
        int,
        int,
        int,
        int,
        list[tuple[str, int]],
        list[tuple[str, int, int, list[int]]],
    ]
] = [
    (
        "farzana",
        "Boutique online store",
        "An online shop for a Dhaka boutique: catalogue, cart and card or mobile-wallet checkout.",
        "React storefront, Node.js API, tidy product photos, tested checkout.",
        9_500_000,
        28,
        9,
        4,
        [("React", 1), ("Node.js", 1), ("UI/UX", 1)],
        [
            ("Brand and layout", 4, 1500, []),
            ("Catalogue and cart", 8, 3000, [0]),
            ("Checkout and payments", 6, 3000, [0]),
            ("Polish and accessibility", 4, 1500, [1, 2]),
            ("Launch checks", 3, 1000, [3]),
        ],
    ),
    (
        "farzana",
        "Clinic appointment portal",
        "Patients book, move and cancel visits; reception sees the day's queue.",
        "React front end, FastAPI back end, PostgreSQL, SMS reminders, tested.",
        11_000_000,
        35,
        11,
        6,
        [("React", 1), ("FastAPI", 1), ("PostgreSQL", 1)],
        [
            ("Requirements", 3, 1000, []),
            ("Data model", 5, 1500, [0]),
            ("Booking API", 10, 3000, [1]),
            ("Booking screens", 10, 2500, [0]),
            ("Reminders and launch", 5, 2000, [2, 3]),
        ],
    ),
    (
        "rahim",
        "Delivery rider tracking",
        "Riders share their position and customers follow the order on a map.",
        "Flutter rider app, FastAPI events API, Docker deployment.",
        7_500_000,
        21,
        6,
        3,
        [("Flutter", 1), ("FastAPI", 1), ("DevOps", 1)],
        [
            ("Rider app skeleton", 5, 2000, []),
            ("Events API", 6, 3000, []),
            ("Live map screen", 6, 2500, [0, 1]),
            ("Deploy and monitor", 4, 2500, [2]),
        ],
    ),
    (
        "farzana",
        "School results dashboard",
        "Teachers enter marks; parents read term reports and class trends.",
        "PostgreSQL reports, React dashboard, regression tests.",
        6_000_000,
        18,
        8,
        5,
        [("PostgreSQL", 1), ("React", 1), ("Testing", 1)],
        [
            ("Schema and imports", 4, 2000, []),
            ("Report queries", 4, 2500, [0]),
            ("Dashboard", 6, 3000, [1]),
            ("Regression tests", 3, 2500, [2]),
        ],
    ),
    (
        "rahim",
        "Restaurant website refresh",
        "A faster, clearer website with the menu, opening hours and online table requests.",
        "UI/UX design, React pages, mobile first.",
        4_500_000,
        14,
        5,
        2,
        [("UI/UX", 1), ("React", 1)],
        [("Design", 4, 3000, []), ("Pages", 6, 4000, [0]), ("Review and launch", 3, 3000, [1])],
    ),
]


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
    res = await create_user(
        settings,
        role="CLIENT",
        email="farzana@devsync.local",
        phone="+8801788888888",
        password=pw[FARZANA],
        display_name="Farzana (Studio Nokshi)",
        verified=True,
        with_totp=False,
    )
    ids[FARZANA] = uuid.UUID(res["user_id"])
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
            ids[slug],
            pid,
            slot_ids[skill],
            seed=1000 + n,
            **plans[outcome],  # type: ignore[arg-type]
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


async def _assert_filter(pid: uuid.UUID, stage: int = 1) -> None:
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
    print(f"seed-demo STAGE={stage}: {eligible} eligible, {len(rejected)} ineligible {reasons}")
    expected = sorted([ReasonCode.TOO_SLOW.value, ReasonCode.NO_SKILL_EVIDENCE.value])
    if eligible != 10 or reasons != expected or result.too_few:
        raise SystemExit(
            f"seed assertion failed: eligible={eligible} (want 10), reasons={reasons} "
            f"(want {expected}), too_few={result.too_few}"
        )


async def _close_ordering_bidding(pid: uuid.UUID) -> None:
    """Demo 2 forms the team (D116): close the ordering project's bidding the way the deadline
    job does — verdicts recorded on the bids, the bidders and the client told, BIDDING → FORMING."""
    async with open_session(DbContext.system(), job=True) as db:
        project = await db.get(Project, pid)
        if project is None:
            raise SystemExit("seeded project missing")
        project.bidding_deadline = datetime.now(UTC) - timedelta(hours=1)
        await db.commit()
    await bidding_jobs.close_due_bidding()
    async with open_session(DbContext.system(), job=True) as db:
        status = await db.scalar(select(Project.status).where(Project.id == pid))
    if status != ProjectStatus.FORMING:
        raise SystemExit(f"seed assertion failed: ordering project is {status}, want FORMING")
    print("seed-demo STAGE=2: bidding closed on the ordering project (FORMING)")


# §18.4 stage 2: a TEAM_PENDING project with a declined invitation, for the repair demo (D116,
# Phase 8). Built through the real services, dated four months out so no reservation overlaps the
# ordering project's period (its eligible bids, D116 team and the golden values stay the same).
REPAIR_DEMO = "Clinic appointment booking"
REPAIR_START_DAYS = 120
REPAIR_SLOTS = ["React", "FastAPI", "PostgreSQL", "Testing"]
# (slug, slot skill, days, price_paisa). Whoever gets the Testing place declines; the other
# Testing bidder is the replacement candidate.
REPAIR_BIDS = [
    ("arif", "React", 18, 2_600_000),
    ("tanvir", "FastAPI", 20, 2_800_000),
    ("sadia", "PostgreSQL", 21, 2_300_000),
    ("imran", "Testing", 19, 2_000_000),
    ("zahid", "Testing", 22, 1_900_000),
]
REPAIR_DECLINES_SLOT = "Testing"
REPAIR_SEED = 20261207
# Milestones with the skills they need, so the repair shows which ones a departure affects.
REPAIR_PLAN = [
    ("Requirements & booking flow", 4, 1500, [], ["React"]),
    ("Database", 5, 1500, [0], ["PostgreSQL"]),
    ("Booking API", 7, 3000, [1], ["FastAPI"]),
    ("Patient screens", 8, 2000, [0], ["React"]),
    ("Testing & launch", 4, 2000, [2, 3], ["Testing"]),
]


def _principal(user_id: uuid.UUID, role: str) -> Principal:
    """The seed acts as each person through the services, as a signed-in session would."""
    return Principal(
        user_id=user_id,
        role=role,
        status="ACTIVE",
        session_id=uuid.uuid4(),
        totp_verified=False,
        step_up_until=None,
    )


async def _as_ctx(user_id: uuid.UUID, role: str, fn: Any) -> Any:
    async with _as(user_id, role) as db:
        ctx = Ctx(
            db=db,
            settings=get_settings(),
            principal=_principal(user_id, role),
            now=get_clock().now(),
        )
        return await fn(ctx)


async def _seed_repair_demo(ids: dict[str, uuid.UUID], skills: dict[str, uuid.UUID]) -> uuid.UUID:
    """Publish → bids → a formation run → confirm (invitations sent) → three accept → one
    declines → the repair job ranks the replacement. Asserts the end state (§18.4)."""
    rahim = ids["rahim"]
    slot_ids: dict[str, uuid.UUID] = {}
    start = get_clock().now().date() + timedelta(days=REPAIR_START_DAYS)
    async with _as(rahim, "CLIENT") as db:
        project = Project(
            client_id=rahim,
            title=REPAIR_DEMO,
            summary="Patients book clinic appointments online; reception confirms them.",
            requirements="Booking calendar, reminders and a reception view.",
            budget_paisa=12_000_000,
            deadline_days=30,
            team_size=len(REPAIR_SLOTS),
            status=ProjectStatus.BIDDING,
            start_date=start,
            bidding_deadline=datetime.now(UTC) + timedelta(days=7),
        )
        db.add(project)
        await db.flush()
        for name in REPAIR_SLOTS:
            slot = ProjectSlot(
                project_id=project.id, skill_id=skills[name], label=f"{name} developer", count=1
            )
            db.add(slot)
            await db.flush()
            slot_ids[name] = slot.id
        await _add_plan(db, project.id, [(n, d, s, pre) for n, d, s, pre, _sk in REPAIR_PLAN])
        await db.flush()
        milestones = (
            await db.scalars(
                select(Milestone)
                .where(Milestone.project_id == project.id)
                .order_by(Milestone.position)
            )
        ).all()
        for m, (_n, _d, _s, _p, needs) in zip(milestones, REPAIR_PLAN, strict=True):
            for name in needs:
                db.add(MilestoneSkill(milestone_id=m.id, skill_id=skills[name]))
        pid = project.id
        await db.commit()
    for slug, slot_name, days, price in REPAIR_BIDS:
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
    # Bidding closes the way the deadline job does it; then a run with the dial at 0 (no newcomer
    # bid), executed here.
    async with open_session(DbContext.system(), job=True) as db:
        row = await db.get(Project, pid)
        assert row is not None  # noqa: S101 - written above
        row.bidding_deadline = datetime.now(UTC) - timedelta(hours=1)
        await db.commit()
    await bidding_jobs.close_due_bidding()
    async with open_session(DbContext.system(), job=True) as db:
        closed = await db.get(Project, pid)
        assert closed is not None  # noqa: S101 - written above
        version, settings = await platform_settings.get_active(db)
        snapshot, params = await formation_svc.build_snapshot(
            db,
            get_clock().now().date(),
            closed,
            settings,
            FormationRunCreate(preset="balanced", min_newcomers=0),
        )
        run = FormationRun(
            project_id=pid,
            requested_by=rahim,
            settings_version=version,
            seed=REPAIR_SEED,
            params=params,
            candidate_snapshot=snapshot,
        )
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()
    await formation_runner.execute_run(run_id)
    await _as_ctx(rahim, "CLIENT", lambda ctx: formation_svc.confirm(ctx, run_id))
    # Everyone accepts except whoever holds the place in REPAIR_DECLINES_SLOT.
    async with open_session(DbContext.system(), job=True) as db:
        invitations = (
            await db.execute(
                select(Invitation.id, TeamMember.developer_id, TeamMember.slot_id)
                .join(TeamMember, TeamMember.id == Invitation.team_member_id)
                .join(Team, Team.id == TeamMember.team_id)
                .where(Team.project_id == pid)
            )
        ).all()
    by_id = {v: k for k, v in ids.items()}
    for inv_id, dev_id, slot_id in invitations:
        if slot_id == slot_ids[REPAIR_DECLINES_SLOT]:
            await _as_ctx(
                dev_id,
                "DEVELOPER",
                lambda ctx, i=inv_id: team_svc.decline(
                    ctx, i, DeclineIn(reason="Booked on another project those weeks.")
                ),
            )
            print(
                f"seed-demo STAGE=2: {by_id.get(dev_id)} declined the {REPAIR_DECLINES_SLOT} place"
            )
        else:
            await _as_ctx(dev_id, "DEVELOPER", lambda ctx, i=inv_id: team_svc.accept(ctx, i))
    async with open_session(DbContext.system(), job=True) as db:
        proposal_id = await db.scalar(
            select(RepairProposal.id)
            .join(Team, Team.id == RepairProposal.team_id)
            .where(Team.project_id == pid)
            .order_by(RepairProposal.created_at.desc())
            .limit(1)
        )
    if proposal_id is None:
        raise SystemExit("seed assertion failed: the decline opened no repair")
    await formation_runner.execute_repair(proposal_id)  # a worker may have done it already
    async with open_session(DbContext.system(), job=True) as db:
        status = await db.scalar(select(Project.status).where(Project.id == pid))
        declined = await db.scalar(
            select(func.count())
            .select_from(TeamMember)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.project_id == pid, TeamMember.status == MemberStatus.DECLINED)
        )
        proposal = await db.get(RepairProposal, proposal_id)
        if proposal is None:
            raise SystemExit("seed assertion failed: the repair proposal vanished")
        state, found = proposal.status.value, len(proposal.candidates or [])
    ready = state == "READY" and found > 0
    if status != ProjectStatus.TEAM_PENDING or declined != 1 or not ready:
        raise SystemExit(
            f"seed assertion failed: repair demo is {status}, {declined} declined, proposal "
            f"{state} with {found} candidates"
        )
    print(
        f"seed-demo STAGE=2: “{REPAIR_DEMO}” is TEAM_PENDING with one declined invitation and "
        f"{found} ranked replacement(s)"
    )
    return pid


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


async def _seed_market(ids: dict[str, uuid.UUID], skills: dict[str, uuid.UUID]) -> list[uuid.UUID]:
    """Farzana's profile and the extra open projects (no bids), so browsing looks like a market."""
    farzana = ids[FARZANA]
    async with _as(farzana, "CLIENT") as db:
        user = await db.get(User, farzana)
        if user is None:
            raise SystemExit("client row missing after create_user")
        user.payment_verified_at = get_clock().now()
        db.add(
            ClientProfile(
                user_id=farzana,
                organization="Studio Nokshi",
                description="A small design studio in Gulshan, Dhaka, building shops and portals "
                "for local businesses.",
            )
        )
        await db.commit()
    created: list[uuid.UUID] = []
    for owner, title, summary, reqs, budget, days, bid_days, start, slots, plan in MARKET_PROJECTS:
        async with _as(ids[owner], "CLIENT") as db:
            project = Project(
                client_id=ids[owner],
                title=title,
                summary=summary,
                requirements=reqs,
                budget_paisa=budget,
                deadline_days=days,
                team_size=sum(n for _skill, n in slots),
                status=ProjectStatus.BIDDING,
                start_date=get_clock().now().date() + timedelta(days=start),
                bidding_deadline=datetime.now(UTC) + timedelta(days=bid_days),
            )
            db.add(project)
            await db.flush()
            for skill_name, count in slots:
                db.add(
                    ProjectSlot(
                        project_id=project.id,
                        skill_id=skills[skill_name],
                        label=f"{skill_name} developer",
                        count=count,
                    )
                )
            await db.flush()
            await _add_plan(db, project.id, plan)
            created.append(project.id)
            await db.commit()
    for pid in created:
        await role_assessments.ensure_links_as_system(pid)
    return created


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
    admin: dict[str, str],
    pw: dict[str, str],
    origin: str,
    cycle_id: uuid.UUID,
    stage: int = 1,
) -> None:
    """Print the demo accounts once (`make demo-reset` saves this to runs/demos/accounts-1.txt).
    `make demo-preflight` reads the `client` line: role, email, password."""
    print(f"=== DEMO ACCOUNTS (STAGE {stage}) ===")
    print(f"client       rahim@devsync.local            {pw['rahim']}")
    print(f"client       farzana@devsync.local          {pw[FARZANA]}")
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


def stage2_market() -> Market:
    """The personas' simulated histories (deterministic: fixed seed, no random developers)."""
    data = json.loads(STAGE2_FILE.read_text(encoding="utf-8"))
    personas = [Persona(**{**p, "domains": tuple(p["domains"])}) for p in data["personas"]]
    params = SimParams(seed=data["seed"], developers=0, clients=data["clients"])
    return simulate_market(params, personas)


def _label(domain: str, used: set[str], n: int) -> str:
    names = PROJECT_NAMES[domain]
    label = names[n % len(names)]
    suffix = 2
    while label in used:
        label = f"{names[n % len(names)]} ({suffix})"
        suffix += 1
    used.add(label)
    return label


async def _seed_computed_reputation(ids: dict[str, uuid.UUID]) -> None:
    """Stage 2: store each persona's simulated completed projects and run the engine (D93)."""
    market = stage2_market()
    async with open_session(DbContext.system(), job=True) as db:
        for dev in market.developers:
            used: set[str] = set()
            for n, proj in enumerate(dev.history):
                db.add(
                    ReputationHistory(
                        developer_id=ids[dev.key],
                        source=ReputationSource.SIMULATED,
                        project_label=_label(proj.domain, used, n),
                        client_key=proj.client_key,
                        domain=SkillDomain(proj.domain),
                        t_days=proj.t_days,
                        deadline_days=proj.deadline_days,
                        gamma_comm=Decimal(proj.gamma_comm),
                        gamma_team=Decimal(proj.gamma_team),
                        internal_slots=[Decimal(v) for v in proj.internal_slots],
                        external_slots=[Decimal(v) for v in proj.external_slots],
                        completed_at=HISTORY_START + HISTORY_SPACING * n,
                        sim_version=market.version,
                    )
                )
        await db.flush()
        version, settings = await platform_settings.get_active(db)
        summary = await reputation_engine.recalculate_all(db, settings, version)
        await db.commit()
    print(
        f"seed-demo STAGE=2: computed reputations for {summary.developers} developers from "
        f"simulated histories (seed {market.seed}); newcomer β {summary.newcomer_review:.3f}"
    )


GOLDEN_FIELDS = ("omega", "x", "xm", "beta", "mu", "t", "c", "p")


async def _computed(ids: dict[str, uuid.UUID]) -> dict[str, dict[str, str | int]]:
    keys = [p["key"] for p in json.loads(STAGE2_FILE.read_text(encoding="utf-8"))["personas"]]
    out: dict[str, dict[str, str | int]] = {}
    async with open_session(DbContext.system(), job=True) as db:
        for key in keys:
            snap = await db.scalar(
                select(ReputationSnapshot).where(ReputationSnapshot.developer_id == ids[key])
            )
            if snap is None or snap.settings_version is None:
                raise SystemExit(f"seed assertion failed: no computed reputation for {key}")
            row: dict[str, str | int] = {f: str(getattr(snap, f)) for f in GOLDEN_FIELDS}
            row["completed_projects"] = snap.completed_projects
            row["distinct_clients"] = snap.distinct_clients
            out[key] = row
    return out


async def _assert_golden(ids: dict[str, uuid.UUID], write: bool) -> None:
    """The stage-2 values for named developers are pinned in a fixture (§17 Phase 6 tests)."""
    computed = await _computed(ids)
    if write:
        GOLDEN_FILE.write_text(json.dumps(computed, indent=2, sort_keys=True) + "\n", "utf-8")
        print(f"seed-demo STAGE=2: wrote {GOLDEN_FILE.name}")
        return
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    if computed != golden:
        diff = {k: (golden.get(k), v) for k, v in computed.items() if golden.get(k) != v}
        raise SystemExit(f"seed assertion failed: stage-2 reputations drifted: {diff}")
    print(f"seed-demo STAGE=2: {len(computed)} computed reputations match the golden fixture")


async def seed_stage1() -> None:
    """Stage 1 (Demo 1): fixed reputation snapshots."""
    await seed_stage(1)


async def seed_stage(stage: int, *, write_golden: bool = False, day: int = 12) -> None:
    check_seed_data()
    settings = get_settings()
    async with open_session(DbContext.system(), job=True) as db:
        skills = await _skill_ids(db)
    needed = {n for p in PROFILES.values() for n in p[3]} | set(SLOTS)
    needed |= {sk for m in MARKET_PROJECTS for sk, _n in m[8]}
    missing = sorted(needed - set(skills))
    if missing:
        raise SystemExit(f"skills not seeded: {missing}; run migrations first")
    pw = demo_passwords([*PROFILES, "rahim", FARZANA, "admin"], os.environ.get("DEMO_PASSWORD"))
    ids = await _make_users(settings, pw)
    admin = await _make_admin(settings, pw["admin"])
    if stage == 1:
        await _seed_reputation(ids)
    await _seed_dev_data(ids, skills)
    if stage == 2:  # the stage number
        await _seed_computed_reputation(ids)
    await _seed_client_profile(ids["rahim"])
    pid, slot_ids = await _seed_project(ids, skills)
    await role_assessments.ensure_links_as_system(pid)  # blueprints, as at publish (§4.4)
    evidence = await _seed_role_results(ids, pid, slot_ids)
    await _seed_bids(ids, pid, slot_ids, evidence)
    await _seed_too_few(ids, skills)
    await _seed_market(ids, skills)
    cycle_id = await _seed_cycle_draft(ids["rahim"], skills)
    await _assert_filter(pid, stage)
    if stage == 2:  # the stage number
        await _assert_golden(ids, write_golden)
        await _close_ordering_bidding(pid)
        await _seed_repair_demo(ids, skills)
        await _seed_inventory(ids, skills, day)
    _print_accounts(admin, pw, settings.PUBLIC_ORIGIN.rstrip("/"), cycle_id, stage)


# --------------------------------------------------------------------------- Inventory (§18.2)

INVENTORY = "Inventory dashboard"
DEFAULT_DAY = 12
DAY_RANGE = (3, 20)  # D170: the fixed history needs day 3; more than 20 days would be stale
# (slot skill, member slug): one bid per place, so the formation run's team is forced. Every one
# of them has ≥ 30 hours a week and commits 10 here, so the ordering project's bids (20 hours,
# starting in 3 days, overlapping this project) stay feasible and its D116 team doesn't move.
INVENTORY_TEAM = [
    ("React", "arif"),
    ("FastAPI", "farhan"),
    ("UI/UX", "nusrat"),
    ("Testing", "imran"),
]
INVENTORY_HOURS = 10
# §18.2 item 2: (name, days, share_bp, predecessors, skills). Planned 23 days; the critical path
# is Requirements → UI design → Dashboard frontend → Integration → Testing; Inventory API has 6
# days of slack.
INVENTORY_PLAN = [
    ("Requirements", 3, 1000, [], ["React"]),
    ("UI design", 5, 1500, [0], ["UI/UX"]),
    ("Inventory API", 7, 2000, [0], ["FastAPI"]),
    ("Dashboard frontend", 8, 2500, [1], ["React"]),
    ("Integration", 3, 1500, [2, 3], ["React", "FastAPI"]),
    ("Testing & handover", 4, 1500, [4], ["Testing"]),
]


def _at(start: date, day: int, hour: int = 10, minute: int = 0) -> datetime:
    """Project day `day` at hh:mm Asia/Dhaka, as UTC."""
    return datetime.combine(
        start + timedelta(days=day), time(hour, minute), tzinfo=DHAKA
    ).astimezone(UTC)


async def _as_ctx_at(user_id: uuid.UUID, role: str, at: datetime, fn: Any) -> Any:
    """Act as a person through the services at a past instant (a FrozenClock per action)."""
    async with _as(user_id, role) as db:
        ctx = Ctx(db=db, settings=get_settings(), principal=_principal(user_id, role), now=at)
        return await fn(ctx)


async def _system_milestone(pid: uuid.UUID, name: str, **values: Any) -> None:
    """Phase 10's milestone transitions (approval, activating a successor) don't exist yet, so the
    seed sets them directly as SYSTEM — the only rows it writes without a service (D154)."""
    async with open_session(DbContext.system(), job=True) as db:
        m = await db.scalar(
            select(Milestone).where(Milestone.project_id == pid, Milestone.name == name)
        )
        if m is None:
            raise SystemExit(f"seed assertion failed: no milestone {name!r}")
        for key, value in values.items():
            setattr(m, key, value)
        await db.commit()


async def _inventory_team(
    ids: dict[str, uuid.UUID], skills: dict[str, uuid.UUID], start: date
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """Publish → bids → formation run → confirm → accept → lead → start, as on the Clinic
    project, with the clock at day −1 (and day 0 for the start). Returns project and milestones."""
    rahim = ids["rahim"]
    eve = _at(start, -1)
    slot_ids: dict[str, uuid.UUID] = {}
    async with _as(rahim, "CLIENT") as db:
        project = Project(
            client_id=rahim,
            title=INVENTORY,
            summary="Stock levels, low-stock alerts and supplier orders for a small warehouse.",
            requirements="React dashboard, FastAPI inventory API, tested hand-over.",
            budget_paisa=12_000_000,
            deadline_days=30,
            team_size=len(INVENTORY_TEAM),
            status=ProjectStatus.BIDDING,
            start_date=start,
            bidding_deadline=datetime.now(UTC) + timedelta(days=1),
        )
        db.add(project)
        await db.flush()
        for name, _slug in INVENTORY_TEAM:
            slot = ProjectSlot(
                project_id=project.id, skill_id=skills[name], label=f"{name} developer", count=1
            )
            db.add(slot)
            await db.flush()
            slot_ids[name] = slot.id
        await _add_plan(db, project.id, [(n, d, s, p) for n, d, s, p, _k in INVENTORY_PLAN])
        await db.flush()
        rows = (
            await db.scalars(
                select(Milestone)
                .where(Milestone.project_id == project.id)
                .order_by(Milestone.position)
            )
        ).all()
        for m, (_n, _d, _s, _p, needs) in zip(rows, INVENTORY_PLAN, strict=True):
            for name in needs:
                db.add(MilestoneSkill(milestone_id=m.id, skill_id=skills[name]))
        pid = project.id
        milestones = {m.name: m.id for m in rows}
        await db.commit()
    for name, slug in INVENTORY_TEAM:
        async with _as(ids[slug], "DEVELOPER") as db:
            db.add(
                Bid(
                    project_id=pid,
                    developer_id=ids[slug],
                    slot_id=slot_ids[name],
                    price_paisa=2_400_000,
                    days_needed=20,
                    hours_per_week_committed=INVENTORY_HOURS,
                    status=BidStatus.ACTIVE,
                )
            )
            await db.commit()
    async with open_session(DbContext.system(), job=True) as db:
        row = await db.get(Project, pid)
        if row is None:
            raise SystemExit("seed assertion failed: the Inventory project vanished")
        row.bidding_deadline = datetime.now(UTC) - timedelta(hours=1)
        await db.commit()
    await bidding_jobs.close_due_bidding()
    async with open_session(DbContext.system(), job=True) as db:
        closed = await db.get(Project, pid)
        if closed is None or closed.status != ProjectStatus.FORMING:
            raise SystemExit("seed assertion failed: the Inventory project didn't start forming")
        version, settings = await platform_settings.get_active(db)
        snapshot, params = await formation_svc.build_snapshot(
            db,
            start - timedelta(days=1),
            closed,
            settings,
            FormationRunCreate(preset="balanced", min_newcomers=0),
        )
        run = FormationRun(
            project_id=pid,
            requested_by=rahim,
            settings_version=version,
            seed=REPAIR_SEED + 1,
            params=params,
            candidate_snapshot=snapshot,
        )
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()
    await formation_runner.execute_run(run_id)
    await _as_ctx_at(rahim, "CLIENT", eve, lambda ctx: formation_svc.confirm(ctx, run_id))
    async with open_session(DbContext.system(), job=True) as db:
        invitations = (
            await db.execute(
                select(Invitation.id, TeamMember.developer_id)
                .join(TeamMember, TeamMember.id == Invitation.team_member_id)
                .join(Team, Team.id == TeamMember.team_id)
                .where(Team.project_id == pid)
            )
        ).all()
    if len(invitations) != len(INVENTORY_TEAM):
        raise SystemExit(f"seed assertion failed: Inventory formed {len(invitations)} places")
    for inv_id, dev_id in invitations:
        await _as_ctx_at(dev_id, "DEVELOPER", eve, lambda ctx, i=inv_id: team_svc.accept(ctx, i))
    async with open_session(DbContext.system(), job=True) as db:
        lead = await db.scalar(
            select(TeamMember.id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.project_id == pid, TeamMember.developer_id == ids["arif"])
        )
        version_now = await db.scalar(select(Project.version).where(Project.id == pid))
    if lead is None:
        raise SystemExit("seed assertion failed: Arif isn't on the Inventory team")
    await _as_ctx_at(
        rahim,
        "CLIENT",
        eve,
        lambda ctx: team_svc.choose_lead(ctx, pid, ChooseLeadIn(member_id=lead), version_now),
    )
    async with open_session(DbContext.system(), job=True) as db:
        version_now = await db.scalar(select(Project.version).where(Project.id == pid))
    await _as_ctx_at(
        rahim, "CLIENT", _at(start, 0, 9), lambda ctx: team_svc.start_project(ctx, pid, version_now)
    )
    return pid, milestones


async def _make_tasks(
    lead: uuid.UUID, at: datetime, milestone: uuid.UUID, specs: list[tuple[str, str, uuid.UUID]]
) -> list[dict[str, Any]]:
    """The lead creates tasks (title, estimate, assignee) in a milestone."""
    out = []
    for title, hours, assignee in specs:
        detail = await _as_ctx_at(
            lead,
            "DEVELOPER",
            at,
            lambda ctx, t=title, h=hours, a=assignee: tasks_svc.create_task(
                ctx,
                milestone,
                TaskCreate(title=t, estimate_hours=Decimal(h), difficulty="MEDIUM", assignee_id=a),
            ),
        )
        out.append({"id": detail.id, "version": detail.version, "assignee": assignee})
    return out


async def _finish(task: dict[str, Any], start: date, day: int, hour: int = 11) -> None:
    """The assignee moves a task To do → In progress → Review → Done on one day."""
    for step, status in enumerate(("IN_PROGRESS", "REVIEW", "DONE")):
        card = await _as_ctx_at(
            task["assignee"],
            "DEVELOPER",
            _at(start, day, hour, step * 15),
            lambda ctx, s=status: tasks_svc.move_task(
                ctx, task["id"], TaskMove(status=s), task["version"]
            ),
        )
        task["version"] = card.version


async def _checkin(
    uid: uuid.UUID, pid: uuid.UUID, at: datetime, blockers: str | None = None
) -> Any:
    body = CheckinCreate(
        done="Worked through this week's tasks on the board.",
        next="The next tasks in my column.",
        blockers=blockers,
        confidence=4,
    )
    return await _as_ctx_at(
        uid, "DEVELOPER", at, lambda ctx: checkins_svc.post_checkin(ctx, pid, body)
    )


async def _seed_inventory(
    ids: dict[str, uuid.UUID], skills: dict[str, uuid.UUID], day: int
) -> None:
    """§18.2 item 2 on project day `day` (default 12): the team works through the real services
    under a frozen clock per simulated day. The history is fixed in project days; `day` only moves
    "today" (events after day 12 are never written, D154). Asserted at day 12: forecast 25 (+2),
    exactly CRITICAL_PATH_DELAY (Dashboard frontend), SLACK_EATEN (Inventory API),
    DEADLINE_IMPACT MEDIUM, INACTIVE_MEMBER MEDIUM (Nusrat, 8 days), health At risk."""
    today = weeks.dhaka_date(datetime.now(UTC))
    start = today - timedelta(days=day)
    last = min(day, DEFAULT_DAY)
    arif, farhan, nusrat, imran = ids["arif"], ids["farhan"], ids["nusrat"], ids["imran"]
    pid, ms = await _inventory_team(ids, skills, start)

    def until(d: int) -> bool:
        return d <= last

    req = await _make_tasks(
        arif,
        _at(start, 0),
        ms["Requirements"],
        [("Stock rules and user roles", "2.0", arif), ("Screens to build", "2.0", arif)],
    )
    ui = await _make_tasks(
        arif,
        _at(start, 0, 10, 30),
        ms["UI design"],
        [
            ("Dashboard wireframes", "2.0", nusrat),
            ("Component styles", "2.0", arif),
            ("Low-stock alert design", "2.0", arif),
        ],
    )
    api = await _make_tasks(
        arif,
        _at(start, 0, 11),
        ms["Inventory API"],
        [(f"Inventory API part {i + 1}", "2.0", farhan) for i in range(10)],
    )
    dash = await _make_tasks(
        arif,
        _at(start, 0, 11, 30),
        ms["Dashboard frontend"],
        [(f"Dashboard view {i + 1}", "1.5", arif) for i in range(10)],
    )
    for who in (arif, farhan, nusrat, imran):
        await _checkin(who, pid, _at(start, 1, 9))
    for i, task in enumerate(req):
        await _finish(task, start, 1 + i)  # done on days 1 and 2
    if until(3):  # Requirements approved on day 3; UI design starts (D154 helper)
        await _system_milestone(
            pid,
            "Requirements",
            status=MilestoneStatus.APPROVED,
            actual_start=start,
            actual_finish=start + timedelta(days=3),
        )
        await _system_milestone(
            pid, "UI design", status=MilestoneStatus.ACTIVE, actual_start=start + timedelta(days=3)
        )
        await _finish(ui[0], start, 3, 22)  # Nusrat's last activity: day 3, 22:00–22:30
    if until(4):
        await _system_milestone(
            pid,
            "Inventory API",
            status=MilestoneStatus.ACTIVE,
            actual_start=start + timedelta(days=4),
        )
    for i, task in enumerate(api[:7]):  # 7 of 10 done → p = 0.7
        if until(4 + i):
            await _finish(task, start, 4 + i, 14)  # days 4 to 10
    for i, task in enumerate(ui[1:]):
        if until(5 + i):
            await _finish(task, start, 5 + i)  # days 5 and 6
    if until(8):  # UI design approved after one revision; the dashboard starts
        await _system_milestone(
            pid,
            "UI design",
            status=MilestoneStatus.APPROVED,
            actual_finish=start + timedelta(days=8),
            revision_count=1,
        )
        await _system_milestone(
            pid,
            "Dashboard frontend",
            status=MilestoneStatus.ACTIVE,
            actual_start=start + timedelta(days=8),
        )
        for who in (arif, farhan):
            await _checkin(who, pid, _at(start, 8, 9))
    for i, task in enumerate(dash[:4]):  # 4 of 10 done → p = 0.4
        if until(8 + i):
            await _finish(task, start, 8 + i, 16)  # days 8 to 11
    if until(9):  # Imran is blocked; Farhan answers the next day
        blocked = await _checkin(
            imran,
            pid,
            _at(start, 9, 9),
            blockers="The stock API's error codes aren't documented yet.",
        )
        if until(10):
            reply = CommentCreate(
                target_type=CommentTarget.CHECKIN,
                target_id=blocked.id,
                body="I've added them to the API notes; see the README.",
            )
            await _as_ctx_at(
                farhan,
                "DEVELOPER",
                _at(start, 10, 10),
                lambda ctx: comments_svc.create_comment(ctx, reply),
            )
    if until(11):
        note = CommentCreate(
            target_type=CommentTarget.TASK,
            target_id=dash[4]["id"],
            body="Next up: the stock table. Can you check the paging params?",
            mention_ids=[farhan],
        )
        await _as_ctx_at(
            arif,
            "DEVELOPER",
            _at(start, 11, 12),
            lambda ctx: comments_svc.create_comment(ctx, note),
        )
        plan_note = CommentCreate(
            target_type=CommentTarget.MILESTONE,
            target_id=ms["Testing & handover"],
            body="Test plan drafted; it starts once integration lands.",
        )
        await _as_ctx_at(
            imran,
            "DEVELOPER",
            _at(start, 11, 15),
            lambda ctx: comments_svc.create_comment(ctx, plan_note),
        )
    result = await monitoring.evaluate_project(pid, datetime.now(UTC))
    await _assert_inventory(pid, day, result)


async def _assert_inventory(pid: uuid.UUID, day: int, result: dict[str, Any]) -> None:
    async with open_session(DbContext.system(), job=True) as db:
        rows = (
            await db.execute(
                select(Risk.type, Risk.severity, Risk.entity_type).where(
                    Risk.project_id == pid, Risk.status == RiskStatus.OPEN
                )
            )
        ).all()
        snap = await db.scalar(
            select(ForecastSnapshot.forecast)
            .where(ForecastSnapshot.project_id == pid)
            .order_by(ForecastSnapshot.day.desc())
            .limit(1)
        )
    found = sorted((t.value, s.value, e) for t, s, e in rows)
    health = snap["health"] if snap else "?"
    print(
        f"seed-demo STAGE=2: “{INVENTORY}” on day {day}: forecast "
        f"{snap['finish_day'] if snap else '?'} (+{result.get('impact_days')}), health {health}, "
        f"risks {', '.join(f'{t} {s}' for t, s, _e in found)}"
    )
    if day != DEFAULT_DAY:
        return
    expected = sorted(
        [
            ("CRITICAL_PATH_DELAY", "CRITICAL", "MILESTONE"),
            ("SLACK_EATEN", "MEDIUM", "MILESTONE"),
            ("DEADLINE_IMPACT", "MEDIUM", "PROJECT"),
            ("INACTIVE_MEMBER", "MEDIUM", "MEMBER"),
        ]
    )
    if (
        snap is None
        or snap["finish_day"] != 25
        or snap["impact_days"] != 2
        or found != expected
        or health != "AT_RISK"
        or snap["overall"] != "CRITICAL"
    ):
        raise SystemExit(
            f"seed assertion failed: Inventory dashboard on day 12 is {found}, "
            f"health {health}, snapshot {snap and snap['finish_day']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="DevSync demo seed")
    parser.add_argument("--stage", type=int, default=1)
    parser.add_argument(
        "--write-golden",
        action="store_true",
        help="stage 2: rewrite scripts/seed_data/stage2_reputation_golden.json (a reviewed change)",
    )
    parser.add_argument(
        "--day",
        type=int,
        default=None,
        help=f"stage 2: the Inventory dashboard's project day ({DAY_RANGE[0]}–{DAY_RANGE[1]}, "
        f"default {DEFAULT_DAY}; D170)",
    )
    args = parser.parse_args()
    stage = args.stage
    if args.day is not None and stage == 1:
        raise SystemExit("DAY needs stage 2: only stage 2 has the Inventory dashboard (D170)")
    day = DEFAULT_DAY if args.day is None else args.day
    if not DAY_RANGE[0] <= day <= DAY_RANGE[1]:
        raise SystemExit(f"DAY must be {DAY_RANGE[0]}–{DAY_RANGE[1]} (D170)")
    if stage not in (1, 2):
        raise SystemExit(f"stage {stage} is not available yet")
    if args.write_golden and stage != 2:  # the stage number
        raise SystemExit("--write-golden applies to stage 2 only")
    asyncio.run(seed_stage(stage, write_golden=args.write_golden, day=day))
    return 0


if __name__ == "__main__":
    sys.exit(main())
