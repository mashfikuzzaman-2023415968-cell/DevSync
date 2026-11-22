"""The route timeout spares exactly the two Server-Sent Events streams (§10.3), nothing else."""

from __future__ import annotations

import uuid

import pytest

from app.core.middleware import SSE_PATHS

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "path",
    ["/api/v1/notifications/stream", f"/api/v1/jobs/{uuid.uuid4()}/events"],
)
def test_sse_streams_are_exempt(path: str) -> None:
    assert SSE_PATHS.match(path)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/jobs/not-a-uuid/events",
        f"/api/v1/jobs/{uuid.uuid4()}",
        f"/api/v1/jobs/{uuid.uuid4()}/events/x",
        "/api/v1/projects/stream",
        "/api/v1/notifications/stream/extra",
        f"/api/v1/admin/jobs/{uuid.uuid4()}/events",
    ],
)
def test_other_paths_keep_the_timeout(path: str) -> None:
    assert not SSE_PATHS.match(path)
