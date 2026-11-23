"""The job event channel refuses anything but the few safe keys (D107)."""

from __future__ import annotations

import uuid

import pytest

from app.api.v1.jobs import _resume_index
from app.core.job_events import publish

pytestmark = pytest.mark.unit


async def test_publish_refuses_unknown_keys() -> None:
    with pytest.raises(ValueError, match="unexpected event keys"):
        await publish(None, uuid.uuid4(), {"progress": 1, "team": ["names"]})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, 0), ("0", 1), ("41", 42), ("-1", 0), ("abc", 0), ("1234567", 0), ("", 0)],
)
def test_resume_index(header: str | None, expected: int) -> None:
    assert _resume_index(header) == expected
