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
from app.core.clock import FrozenClock
from app.core.config import Environment, Settings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient

TEST_HOST = "testserver"


def make_settings(**overrides: object) -> Settings:
    """Settings for tests: test environment, test host allowed, everything else default."""
    base: dict[str, object] = {"DEVSYNC_ENV": Environment.TEST, "ALLOWED_HOSTS": TEST_HOST}
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

    engine = create_async_engine(app_db_url)
    async with engine.connect() as conn:
        tx = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await tx.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
