"""Opaque server-side sessions (spec §5.3 decision 1, §14.4).

The browser holds only a random 256-bit token in the `__Host-ds_session` cookie
(HttpOnly, Secure, SameSite=Lax, Path=/, no Domain). The server stores its SHA-256:
in Redis for speed and in the `sessions` table for listing, revocation and
recovery after a Redis restart.

Timing rules:
- the token is rotated on the first request after it is 15 minutes old; the old
  token keeps working for a 30-second grace window so in-flight requests succeed;
- idle timeout 30 minutes (15 for admins); absolute lifetime 7 days;
- rotation also happens on login, privilege change and step-up.
"""

from __future__ import annotations

import base64
import json
import secrets
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import column, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.netutil import valid_ip
from app.core.security import generate_token, token_digest
from app.models.identity import Session as SessionRow

SESSION_COOKIE = "__Host-ds_session"
ROTATION_GRACE_SECONDS = 30
ADMIN_IDLE_MINUTES = 15
LAST_SEEN_DB_WRITE_SECONDS = 60
REDIS_PREFIX = "sess:"
USER_INDEX_PREFIX = "usersess:"


@dataclass(frozen=True)
class SessionData:
    """Everything the server knows about one session (never sent to the browser)."""

    session_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    status: str
    csrf_secret: bytes
    created_at: datetime
    last_seen_at: datetime
    rotated_at: datetime
    expires_at: datetime
    step_up_until: datetime | None
    totp_verified: bool
    last_db_write: datetime

    def to_json(self) -> str:
        """Serialize for Redis."""
        data: dict[str, Any] = asdict(self)
        data["session_id"] = str(self.session_id)
        data["user_id"] = str(self.user_id)
        data["csrf_secret"] = base64.b64encode(self.csrf_secret).decode()
        for key in ("created_at", "last_seen_at", "rotated_at", "expires_at", "last_db_write"):
            data[key] = getattr(self, key).isoformat()
        data["step_up_until"] = self.step_up_until.isoformat() if self.step_up_until else None
        return json.dumps(data)

    @classmethod
    def from_json(cls, raw: str | bytes) -> SessionData:
        """Inverse of :meth:`to_json`."""
        d = json.loads(raw)
        return cls(
            session_id=uuid.UUID(d["session_id"]),
            user_id=uuid.UUID(d["user_id"]),
            role=d["role"],
            status=d["status"],
            csrf_secret=base64.b64decode(d["csrf_secret"]),
            created_at=datetime.fromisoformat(d["created_at"]),
            last_seen_at=datetime.fromisoformat(d["last_seen_at"]),
            rotated_at=datetime.fromisoformat(d["rotated_at"]),
            expires_at=datetime.fromisoformat(d["expires_at"]),
            step_up_until=(
                datetime.fromisoformat(d["step_up_until"]) if d["step_up_until"] else None
            ),
            totp_verified=bool(d["totp_verified"]),
            last_db_write=datetime.fromisoformat(d["last_db_write"]),
        )


class SessionPolicy:
    """Timeouts derived from settings (§6.1)."""

    def __init__(self, settings: Settings) -> None:
        self.rotate = timedelta(minutes=settings.SESSION_ROTATE_MINUTES)
        self.idle = timedelta(minutes=settings.SESSION_IDLE_MINUTES)
        self.admin_idle = timedelta(minutes=min(ADMIN_IDLE_MINUTES, settings.SESSION_IDLE_MINUTES))
        self.absolute = timedelta(hours=settings.SESSION_ABSOLUTE_HOURS)

    def idle_for(self, role: str) -> timedelta:
        """Idle timeout for a role (admins get the shorter one, §14.17)."""
        return self.admin_idle if role == "ADMIN" else self.idle

    def is_expired(self, data: SessionData, now: datetime) -> bool:
        """Absolute or idle expiry reached."""
        return now >= data.expires_at or now - data.last_seen_at >= self.idle_for(data.role)

    def needs_rotation(self, data: SessionData, now: datetime) -> bool:
        """Token older than the rotation interval."""
        return now - data.rotated_at >= self.rotate

    def redis_ttl(self, data: SessionData, now: datetime) -> int:
        """Seconds until the Redis copy should vanish (idle or absolute, whichever first)."""
        remaining = min(data.expires_at - now, self.idle_for(data.role))
        return max(1, int(remaining.total_seconds()))


def _key(token_hash: bytes) -> str:
    return REDIS_PREFIX + token_hash.hex()


class SessionStore:
    """Create, load, rotate and revoke sessions (Redis + database)."""

    def __init__(self, redis: Redis, policy: SessionPolicy) -> None:
        self.redis = redis
        self.policy = policy

    async def _cache(self, token_hash: bytes, data: SessionData, now: datetime) -> None:
        await self.redis.set(_key(token_hash), data.to_json(), ex=self.policy.redis_ttl(data, now))
        await self.redis.sadd(USER_INDEX_PREFIX + str(data.user_id), token_hash.hex())

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        role: str,
        status: str,
        now: datetime,
        ip: str | None,
        user_agent: str | None,
        totp_verified: bool = False,
    ) -> tuple[str, SessionData]:
        """New session (caller has set the DB context to `user_id`). Returns (token, data)."""
        token = generate_token(32)
        token_hash = token_digest(token)
        csrf_secret = secrets.token_bytes(32)
        expires_at = now + self.policy.absolute
        row = SessionRow(
            user_id=user_id,
            token_hash=token_hash,
            csrf_secret=csrf_secret,
            ip=valid_ip(ip),
            user_agent=(user_agent or "")[:256] or None,
            created_at=now,
            last_seen_at=now,
            rotated_at=now,
            expires_at=expires_at,
            totp_verified=totp_verified,
        )
        db.add(row)
        await db.flush()
        data = SessionData(
            session_id=row.id,
            user_id=user_id,
            role=role,
            status=status,
            csrf_secret=csrf_secret,
            created_at=now,
            last_seen_at=now,
            rotated_at=now,
            expires_at=expires_at,
            step_up_until=None,
            totp_verified=totp_verified,
            last_db_write=now,
        )
        await self._cache(token_hash, data, now)
        return token, data

    async def load(self, db: AsyncSession, token: str, now: datetime) -> SessionData | None:
        """Look up a token: Redis first, then the database (Redis restarted). None if invalid."""
        token_hash = token_digest(token)
        raw = await self.redis.get(_key(token_hash))
        if raw is not None:
            data = SessionData.from_json(raw)
        else:
            restored = await self._restore_from_db(db, token_hash)
            if restored is None:
                return None
            data = restored
            if not self.policy.is_expired(data, now):
                await self._cache(token_hash, data, now)
        if self.policy.is_expired(data, now):
            await self.redis.delete(_key(token_hash))
            return None
        return data

    async def _restore_from_db(self, db: AsyncSession, token_hash: bytes) -> SessionData | None:
        fields = (
            "session_id", "user_id", "csrf_secret", "created_at", "last_seen_at", "rotated_at",
            "expires_at", "step_up_until", "totp_verified", "role", "status",
        )  # fmt: skip
        stmt: Any = select(*(column(f) for f in fields)).select_from(
            func.auth_session_restore(token_hash)
        )
        row = (await db.execute(stmt)).mappings().first()
        if row is None:
            return None
        return SessionData(
            session_id=row["session_id"],
            user_id=row["user_id"],
            role=str(row["role"]),
            status=str(row["status"]),
            csrf_secret=bytes(row["csrf_secret"]),
            created_at=row["created_at"],
            last_seen_at=row["last_seen_at"],
            rotated_at=row["rotated_at"],
            expires_at=row["expires_at"],
            step_up_until=row["step_up_until"],
            totp_verified=bool(row["totp_verified"]),
            last_db_write=row["last_seen_at"],
        )

    async def touch(
        self, db: AsyncSession, token: str, data: SessionData, now: datetime
    ) -> SessionData:
        """Record activity; writes `last_seen_at` to the DB at most once a minute."""
        token_hash = token_digest(token)
        updated = replace(data, last_seen_at=now)
        if (now - data.last_db_write).total_seconds() >= LAST_SEEN_DB_WRITE_SECONDS:
            await db.execute(
                update(SessionRow).where(SessionRow.id == data.session_id).values(last_seen_at=now)
            )
            updated = replace(updated, last_db_write=now)
        await self._cache(token_hash, updated, now)
        return updated

    async def rotate(
        self, db: AsyncSession, old_token: str, data: SessionData, now: datetime, **changes: Any
    ) -> tuple[str, SessionData]:
        """Issue a new token for the same session; the old one lives 30 s more (grace)."""
        old_hash = token_digest(old_token)
        new_token = generate_token(32)
        new_hash = token_digest(new_token)
        new_data = replace(data, rotated_at=now, last_seen_at=now, last_db_write=now, **changes)
        db_changes: dict[str, Any] = {
            "token_hash": new_hash,
            "rotated_at": now,
            "last_seen_at": now,
        }
        for key in ("step_up_until", "totp_verified"):
            if key in changes:
                db_changes[key] = changes[key]
        await db.execute(
            update(SessionRow).where(SessionRow.id == data.session_id).values(**db_changes)
        )
        await self._cache(new_hash, new_data, now)
        await self.redis.expire(_key(old_hash), ROTATION_GRACE_SECONDS)
        await self.redis.srem(USER_INDEX_PREFIX + str(data.user_id), old_hash.hex())
        return new_token, new_data

    async def revoke(self, db: AsyncSession, token: str, data: SessionData, now: datetime) -> None:
        """End one session everywhere."""
        await self.revoke_by_id(db, data.user_id, data.session_id, now)
        await self.redis.delete(_key(token_digest(token)))

    async def revoke_by_id(
        self, db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, now: datetime
    ) -> bool:
        """Revoke a session by id (device list). True if a live session was revoked."""
        result = await db.execute(
            update(SessionRow)
            .where(
                SessionRow.id == session_id,
                SessionRow.user_id == user_id,
                SessionRow.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .returning(SessionRow.token_hash)
        )
        token_hash = result.scalar_one_or_none()
        if token_hash is None:
            return False
        await self.redis.delete(_key(bytes(token_hash)))
        await self.redis.srem(USER_INDEX_PREFIX + str(user_id), bytes(token_hash).hex())
        return True

    async def revoke_all(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        now: datetime,
        *,
        except_id: uuid.UUID | None = None,
    ) -> int:
        """Revoke every live session of a user (logout-all, password reset). Returns count."""
        stmt = (
            update(SessionRow)
            .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(SessionRow.token_hash)
        )
        if except_id is not None:
            stmt = stmt.where(SessionRow.id != except_id)
        hashes = [bytes(h) for h in (await db.execute(stmt)).scalars().all()]
        for h in hashes:
            await self.redis.delete(_key(h))
            await self.redis.srem(USER_INDEX_PREFIX + str(user_id), h.hex())
        return len(hashes)
