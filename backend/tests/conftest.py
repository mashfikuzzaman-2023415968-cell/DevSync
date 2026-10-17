"""Shared fixtures (spec §16.3). Phase 0 subset: settings, app client, frozen clock, DB/Redis.

Integration fixtures connect to the Postgres/Redis of the test compose stack
(DECISIONS.md D2) using the same roles as production: migrations run as
`devsync_migrator`, application queries as `devsync_app`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.clock import FrozenClock
from app.core.config import Environment, Settings, get_settings
from app.main import create_app
from tests.helpers import Api, stack_available, stack_settings

TEST_HOST = "testserver"


def make_settings(**overrides: object) -> Settings:
    """Test environment, test host, test keys; everything else default."""
    base: dict[str, object] = {
        "DEVSYNC_ENV": Environment.TEST,
        "ALLOWED_HOSTS": TEST_HOST,
        "PUBLIC_ORIGIN": "https://testserver",
        "SECRET_KEY": "test-secret-key-" * 4,
        "CAPTCHA_HMAC_KEY": "test-captcha-key-" * 2,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    """Plain test settings."""
    return make_settings()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """TestClient for an app built with test settings (no DB needed for these routes)."""
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def frozen_clock() -> FrozenClock:
    """A clock frozen at a fixed instant (Mon 12 Oct 2026 04:00 UTC = 10:00 Dhaka)."""
    return FrozenClock(datetime(2026, 10, 12, 4, 0, tzinfo=UTC))


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} not set: integration tests run inside the test compose stack")
    return value


@pytest.fixture(scope="session")
def migration_url() -> str:
    """Sync URL for the migrator role."""
    return _require_env("MIGRATION_DATABASE_URL")


@pytest.fixture(scope="session")
def app_db_url() -> str:
    """Async URL for the application role (DML only)."""
    return _require_env("DATABASE_URL")


@pytest.fixture(scope="session")
def migrated(migration_url: str) -> str:
    """Upgrade the test database to head once per session."""
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    return migration_url


@pytest.fixture
async def app_session(migrated: str, app_db_url: str) -> AsyncIterator[object]:
    """AsyncSession as `devsync_app`, rolled back after the test."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: PLC0415

    from app.db.context import RlsSession  # noqa: PLC0415

    engine = create_async_engine(app_db_url)
    async with engine.connect() as conn:
        tx = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            sync_session_class=RlsSession,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await tx.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clear_process_caches() -> Iterator[None]:
    """Each test gets fresh settings, Redis client, engines and settings cache
    (async clients are bound to the event loop that created them)."""
    from app.core import settings_cache  # noqa: PLC0415
    from app.core.redis import forget_clients  # noqa: PLC0415
    from app.db import session as db_session  # noqa: PLC0415

    def clear() -> None:
        get_settings.cache_clear()
        forget_clients()
        settings_cache.clear()
        for fn in (
            db_session.get_engine,
            db_session.get_job_engine,
            db_session.get_sessionmaker,
            db_session.get_job_sessionmaker,
        ):
            fn.cache_clear()

    clear()
    yield
    clear()


def _flush_redis() -> None:
    """Rate-limit counters, sessions and CAPTCHA markers must not leak between tests
    (every TestClient request comes from the same address)."""
    import redis  # noqa: PLC0415

    client = redis.Redis.from_url(os.environ["REDIS_URL"])
    try:
        client.flushdb()
    finally:
        client.close()


@pytest.fixture
def api(migrated: str) -> Iterator[Api]:
    """HTTPS client against an in-process app using the stack's Postgres and Redis."""
    if not stack_available():
        pytest.skip("needs the test compose stack")
    _flush_redis()
    with TestClient(create_app(stack_settings()), base_url="https://testserver") as c:
        yield Api(c)


@pytest.fixture
def api2(migrated: str) -> Iterator[Api]:
    """A second, independent browser (separate cookies)."""
    if not stack_available():
        pytest.skip("needs the test compose stack")
    with TestClient(create_app(stack_settings()), base_url="https://testserver") as c:
        yield Api(c)
