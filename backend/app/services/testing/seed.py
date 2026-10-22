"""Seeding helpers for the test-only router and `scripts/create_admin.py`.

They run as the worker database role in SYSTEM context (the only context allowed
to insert users directly or create admins under row-level security).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pyotp
from sqlalchemy import delete, select

from app.core.audit import write_audit
from app.core.clock import get_clock
from app.core.config import Settings
from app.core.security import encrypt, generate_recovery_codes, hash_password
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
from app.models.profiles import DeveloperSkill, EvidenceSource, Skill, SkillEvidence
from app.models.projects import Project
from app.models.reputation import ReputationSnapshot
from app.services.auth.common import totp_key


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
) -> dict[str, Any]:
    """Create a user (ACTIVE when `verified`); admins get TOTP + recovery codes."""
    now = get_clock().now()
    async with open_session(DbContext.system(), job=True) as db:
        user = User(
            email=email,
            phone_e164=phone,
            password_hash=hash_password(password),
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
            db.add_all(RecoveryCode(user_id=user.id, code_hash=hash_password(c)) for c in codes)
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
