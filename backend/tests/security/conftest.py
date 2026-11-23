"""Fixtures shared by the security tests of formation and teams (Phases 7–8)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers import ORIGIN, Api, stack_available, stack_settings
from tests.security.formation_world import make_world


@pytest.fixture
def api3(migrated: str) -> Iterator[Api]:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    with TestClient(create_app(stack_settings()), base_url=ORIGIN) as c:
        yield Api(c)


@pytest.fixture
def world(api: Api, api2: Api, migration_url: str) -> dict[str, Any]:
    """Client (api) with a FORMING project and five bidders; api2 is left signed in as the
    last bidder."""
    return make_world(api, api2, migration_url)
