"""SessionStore and RateLimiter against real Redis and Postgres (spec §14.4, §14.8, §16.8)."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from app.core.clock import get_clock
from app.core.ratelimit import RateLimited, RateLimiter, RateLimitUnavailable, Rule
from app.core.redis import get_redis
from app.core.security import hash_password
from app.core.sessions import SessionPolicy, SessionStore
from app.db.context import DbContext
from app.db.session import open_session
from app.models.identity import Session, User, UserRole, UserStatus
from tests.helpers import stack_available, stack_settings, unique_email

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _stack(migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")


async def _user() -> uuid.UUID:
    async with open_session(DbContext.system(), job=True) as db:
        u = User(
            email=unique_email(),
            role=UserRole.CLIENT,
            status=UserStatus.ACTIVE,
            display_name="S",
            password_hash=hash_password("store test password 1!"),
        )
        db.add(u)
        await db.flush()
        uid = u.id
        await db.commit()
    return uid


def _store() -> SessionStore:
    return SessionStore(get_redis(), SessionPolicy(stack_settings()))


async def _create(uid: uuid.UUID) -> tuple[str, object]:
    now = get_clock().now()
    async with open_session(DbContext(user_id=uid, role="CLIENT")) as db:
        token, data = await _store().create(
            db,
            user_id=uid,
            role="CLIENT",
            status="ACTIVE",
            now=now,
            ip="203.0.113.7",
            user_agent="pytest",
        )
        await db.commit()
    return token, data


async def test_restore_from_db_after_redis_loss_and_expiry() -> None:
    uid = await _user()
    token, data = await _create(uid)
    store = _store()
    await get_redis().flushdb()
    now = get_clock().now()
    async with open_session(DbContext.guest()) as db:
        restored = await store.load(db, token, now)
        assert restored is not None
        assert restored.session_id == data.session_id  # type: ignore[attr-defined]
        await get_redis().flushdb()
        assert await store.load(db, token, now + timedelta(days=8)) is None  # absolute expiry
        assert await store.load(db, "unknown-token-value", now) is None


async def test_touch_writes_last_seen_at_most_once_a_minute() -> None:
    uid = await _user()
    token, data = await _create(uid)
    store = _store()
    async with open_session(DbContext(user_id=uid, role="CLIENT")) as db:
        later = get_clock().now() + timedelta(seconds=61)
        touched = await store.touch(db, token, data, later)  # type: ignore[arg-type]
        await db.commit()
        assert touched.last_db_write == later
        soon = later + timedelta(seconds=5)
        again = await store.touch(db, token, touched, soon)
        assert again.last_db_write == later  # no DB write within the minute
        row = (
            await db.execute(select(Session).where(Session.id == touched.session_id))
        ).scalar_one()
        assert row.last_seen_at == later


async def test_revoke_all_except_current_and_revoke_unknown() -> None:
    uid = await _user()
    keep_token, keep = await _create(uid)
    _other_token, _other = await _create(uid)
    store = _store()
    now = get_clock().now()
    async with open_session(DbContext(user_id=uid, role="CLIENT")) as db:
        revoked = await store.revoke_all(db, uid, now, except_id=keep.session_id)  # type: ignore[attr-defined]
        assert revoked == 1
        assert not await store.revoke_by_id(db, uid, uuid.uuid4(), now)
        await db.commit()
        assert await store.load(db, keep_token, now) is not None


async def test_rotation_keeps_old_token_for_grace_then_expires() -> None:
    uid = await _user()
    token, data = await _create(uid)
    store = _store()
    now = get_clock().now()
    async with open_session(DbContext(user_id=uid, role="CLIENT")) as db:
        new_token, _new = await store.rotate(db, token, data, now)  # type: ignore[arg-type]
        await db.commit()
        ttl = await get_redis().ttl("sess:" + hashlib.sha256(token.encode()).hexdigest())
        assert 0 < ttl <= 30
        assert await store.load(db, new_token, now) is not None


async def test_rate_limiter_blocks_and_window_resets() -> None:
    limiter = RateLimiter(get_redis())
    key = uuid.uuid4().hex
    rules = [Rule(limit=2, window_seconds=1)]
    await limiter.hit("comment", key, rules)
    await limiter.hit("comment", key, rules)
    with pytest.raises(RateLimited) as exc:
        await limiter.hit("comment", key, rules)
    assert 1 <= exc.value.retry_after <= 1
    await asyncio.sleep(1.1)
    await limiter.hit("comment", key, rules)  # window passed
    await limiter.reset("comment", key, rules)
    await limiter.hit("comment", key, rules)


async def test_multiple_windows_apply() -> None:
    limiter = RateLimiter(get_redis())
    key = uuid.uuid4().hex
    rules = [Rule(limit=5, window_seconds=60), Rule(limit=1, window_seconds=60)]
    await limiter.hit("bid", key, rules)
    with pytest.raises(RateLimited):
        await limiter.hit("bid", key, rules)


async def test_redis_down_fails_closed_for_auth_and_open_for_reads() -> None:
    dead = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2, socket_timeout=0.2)
    limiter = RateLimiter(dead)
    with pytest.raises(RateLimitUnavailable):
        await limiter.hit("login", "k", [Rule(5, 60)])
    await limiter.hit("api_anonymous", "k", [Rule(60, 60)])  # fails open, no exception
    await limiter.reset("login", "k", [Rule(5, 60)])  # logged, not raised
    await dead.aclose()


def test_policy_ttl_uses_admin_idle() -> None:
    pol = SessionPolicy(stack_settings())
    assert pol.idle_for("ADMIN") < pol.idle_for("CLIENT")
