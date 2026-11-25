"""Seeding helpers for the test-only router and `scripts/create_admin.py`.

They run as the worker database role in SYSTEM context (the only context allowed
to insert users directly or create admins under row-level security).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pyotp
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.simulator import Persona, SimParams, simulate_market
from app.core.audit import write_audit
from app.core.clock import get_clock
from app.core.config import Settings
from app.core.security import (
    encrypt,
    generate_recovery_codes,
    hash_password_async,
    hash_passwords_async,
)
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.identity import (
    EmailOutbox,
    RecoveryCode,
    TotpCredential,
    User,
    UserRole,
    UserStatus,
)
from app.models.profiles import (
    DeveloperSkill,
    EvidenceSource,
    Question,
    Skill,
    SkillDomain,
    SkillEvidence,
    TestAttempt,
)
from app.models.projects import Project, ProjectStatus
from app.models.reputation import ReputationHistory, ReputationSnapshot, ReputationSource
from app.services import bids as bids_svc
from app.services import formation_runner, platform_settings, reputation_engine
from app.services.auth.common import totp_key


async def _phone_taken(db: AsyncSession, phone: str) -> bool:
    return await db.scalar(select(User.id).where(User.phone_e164 == phone)) is not None


async def create_user(
    settings: Settings,
    *,
    role: str,
    email: str,
    phone: str | None,
    password: str,
    display_name: str,
    verified: bool,
    with_totp: bool,
    actor: str = "test-seed",
    swap_taken_phone: bool = False,
) -> dict[str, Any]:
    """Create a user (ACTIVE when `verified`); admins get TOTP + recovery codes. With
    `swap_taken_phone` (the test router only), a phone number already in use is replaced by a
    free one and the number used is returned."""
    now = get_clock().now()
    password_hash = await hash_password_async(password)  # before the transaction opens
    async with open_session(DbContext.system(), job=True) as db:
        # Test runs pile up users in one database, and random numbers from the 8-digit
        # Bangladeshi range start to collide.
        while swap_taken_phone and phone is not None and await _phone_taken(db, phone):
            phone = f"+88017{secrets.randbelow(90_000_000) + 10_000_000}"
        user = User(
            email=email,
            phone_e164=phone,
            password_hash=password_hash,
            role=UserRole(role),
            status=UserStatus.ACTIVE if verified else UserStatus.PENDING,
            display_name=display_name,
            email_verified_at=now if verified else None,
            phone_verified_at=now if verified and phone else None,
        )
        db.add(user)
        await db.flush()
        result: dict[str, Any] = {
            "user_id": str(user.id),
            "phone": phone,
            "totp_secret": None,
            "recovery_codes": [],
        }
        if role == "ADMIN" and with_totp:
            secret = pyotp.random_base32()
            db.add(
                TotpCredential(
                    user_id=user.id,
                    secret_encrypted=encrypt(
                        totp_key(settings), secret.encode(), str(user.id).encode()
                    ),
                    confirmed_at=now,
                )
            )
            codes = generate_recovery_codes()
            code_hashes = await hash_passwords_async(codes)
            db.add_all(RecoveryCode(user_id=user.id, code_hash=h) for h in code_hashes)
            result.update(totp_secret=secret, recovery_codes=codes)
        await write_audit(
            db,
            action="user.seeded",
            entity_type="user",
            entity_id=user.id,
            actor_role=actor,
            after={"role": role, "verified": verified},
        )
        await db.commit()
    return result


async def latest_email_link(to: str, template: str) -> str | None:
    """The `link` placeholder of the newest outbox email (test environment only)."""
    async with open_session(DbContext.system(), job=True) as db:
        row = (
            await db.execute(
                select(EmailOutbox.payload)
                .where(EmailOutbox.to_email == to, EmailOutbox.template == template)
                .order_by(EmailOutbox.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    link = row.get("link") if isinstance(row, dict) else None
    return str(link) if link else None


# --------------------------------------------------------------------------- Phase 5 E2E state
# Bidding scenarios need states a browser can't reach quickly: a passed bidding deadline, a
# developer's skill with test evidence (the newcomer rule), an experienced reputation.


async def close_bidding(project_id: uuid.UUID) -> bool:
    """Move a project's bidding deadline one minute into the past (the job hasn't run yet)."""
    async with open_session(DbContext.system(), job=True) as db:
        project = await db.get(Project, project_id)
        if project is None:
            return False
        project.bidding_deadline = get_clock().now() - timedelta(minutes=1)
        await db.commit()
    return True


async def add_skill_evidence(user_id: uuid.UUID, skill_name: str, score: Decimal) -> bool:
    """Give a developer a listed skill and a passing (or not) TEST evidence score for it."""
    async with open_session(DbContext.system(), job=True) as db:
        skill_id = await db.scalar(select(Skill.id).where(Skill.name == skill_name))
        if skill_id is None:
            return False
        existing = await db.scalar(
            select(DeveloperSkill.id).where(
                DeveloperSkill.user_id == user_id, DeveloperSkill.skill_id == skill_id
            )
        )
        if existing is None:
            db.add(DeveloperSkill(user_id=user_id, skill_id=skill_id, self_level=3))
        db.add(
            SkillEvidence(
                user_id=user_id,
                skill_id=skill_id,
                source=EvidenceSource.TEST,
                score=score,
                at=get_clock().now(),
            )
        )
        await db.commit()
    return True


async def set_reputation(user_id: uuid.UUID, p: Decimal, c: Decimal) -> None:
    """Store an experienced developer's reputation snapshot (Phase 5 reads snapshots only)."""
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(
            delete(ReputationSnapshot).where(ReputationSnapshot.developer_id == user_id)
        )
        db.add(
            ReputationSnapshot(
                developer_id=user_id,
                omega=Decimal("0.600"),
                x=Decimal("0.700"),
                xm=Decimal("0.660"),
                beta=Decimal("0.800"),
                mu=Decimal("0.700"),
                t=Decimal("0.800"),
                c=c,
                p=p,
                completed_projects=6,
                distinct_clients=4,
            )
        )
        await db.commit()


async def answer_key(attempt_id: uuid.UUID) -> list[int] | None:
    """The correct option index of each question of an attempt, in the order the attempt shows
    them (test environment only: the Demo 1 walkthrough passes a timed test through the UI)."""
    async with open_session(DbContext.system(), job=True) as db:
        attempt = await db.get(TestAttempt, attempt_id)
        if attempt is None:
            return None
        question_ids = list(attempt.question_ids)
        rows = await db.execute(
            select(Question.id, Question.correct_index).where(Question.id.in_(question_ids))
        )
        correct = {qid: int(idx) for qid, idx in rows.all()}
    return [correct[qid] for qid in question_ids]


async def seed_reputation_history(user_id: uuid.UUID, projects: int, seed: int) -> None:
    """Give a developer `projects` simulated completed projects and run the engine for them
    (E2E and API tests of the Phase 6 reputation screens). Test environment only."""
    persona = Persona(key="test", domains=("FRONTEND", "BACKEND"), projects=projects,
                      clients=max(1, (projects + 1) // 2), skill=0.75, reliability=0.7,
                      teamwork=0.7, communication=0.75)  # fmt: skip
    market = simulate_market(SimParams(seed=seed, developers=0, clients=12), [persona])
    start = datetime(2025, 1, 1, 12, tzinfo=UTC)
    async with open_session(DbContext.system(), job=True) as db:
        for n, proj in enumerate(market.developers[0].history):
            db.add(
                ReputationHistory(
                    developer_id=user_id,
                    source=ReputationSource.SIMULATED,
                    project_label=f"Simulated project {n + 1}",
                    client_key=proj.client_key,
                    domain=SkillDomain(proj.domain),
                    t_days=proj.t_days,
                    deadline_days=proj.deadline_days,
                    gamma_comm=Decimal(proj.gamma_comm),
                    gamma_team=Decimal(proj.gamma_team),
                    internal_slots=[Decimal(v) for v in proj.internal_slots],
                    external_slots=[Decimal(v) for v in proj.external_slots],
                    completed_at=start + timedelta(days=30 * n),
                    sim_version=market.version,
                )
            )
        await db.flush()
        version, settings = await platform_settings.get_active(db)
        await reputation_engine.recalculate(db, user_id, settings, version)
        await db.commit()


async def execute_formation_run(run_id: uuid.UUID) -> str:
    """Run a queued formation run in this process (E2E: the test stack has no worker). Returns
    the run's final status; a run that already started is left alone."""
    return (await formation_runner.execute_run(run_id)).value


async def write_formation_explanations(run_id: uuid.UUID) -> int:
    """Write a confirmed run's "why not selected" rows now (E2E)."""
    return (await formation_runner.write_explanations(run_id))["explanations"]


async def start_forming(project_id: uuid.UUID) -> bool:
    """Close bidding the way the deadline job does — the verdicts recorded on the bids and
    BIDDING → FORMING — without waiting for the scheduler (E2E: the test stack runs none).
    False when the project is unknown, not BIDDING or still short of eligible bids."""
    now = get_clock().now()
    async with open_session(DbContext.system(), job=True) as db:
        project = await db.get(Project, project_id, with_for_update=True)
        if project is None or project.status != ProjectStatus.BIDDING:
            return False
        project.bidding_deadline = now - timedelta(minutes=1)
        settings = await active_settings(db)
        ev = await bids_svc.evaluate(db, project, settings, now.date())
        if ev.result.too_few:
            return False
        bids_svc.record_evaluation(ev, now)
        project.status = ProjectStatus.FORMING
        project.version += 1
        await db.commit()
    return True


async def execute_repair(proposal_id: uuid.UUID) -> str:
    """Rank a queued repair proposal now (E2E: no worker, D133)."""
    return await formation_runner.execute_repair(proposal_id)


async def run_lifecycle_expire() -> dict[str, int]:
    """The invitation and reopened-slot part of `lifecycle.expire`, now (E2E: no scheduler)."""
    from app.services import repair as repair_svc  # noqa: PLC0415
    from app.services import team as team_svc  # noqa: PLC0415

    now = get_clock().now()
    counts = await team_svc.expire_due(now)
    counts["slots_closed"] = await repair_svc.close_reopened(now)
    return counts


async def set_invitation_expiry(invitation_id: uuid.UUID, expires_at: datetime) -> bool:
    """Move a sent invitation's expiry (E2E: countdown and expiry states, D133)."""
    from app.models.formation import Invitation  # noqa: PLC0415

    async with open_session(DbContext.system(), job=True) as db:
        inv = await db.get(Invitation, invitation_id)
        if inv is None or inv.sent_at is None:
            return False
        inv.expires_at = expires_at
        await db.commit()
    return True
