"""Readiness against the real Postgres and Redis of the test stack."""

from __future__ import annotations

import pytest
from app.services.health import check_dependencies

pytestmark = pytest.mark.integration


async def test_all_dependencies_ready(migrated: str) -> None:
    assert await check_dependencies() == {"database": "ok", "redis": "ok", "queue": "ok"}
