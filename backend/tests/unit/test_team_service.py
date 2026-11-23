"""The parts of the team service that need no database (D118, D121, D123): invitation states,
which places still need an accepted member, the milestone start guard and the inactivity signal."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.models.formation import InvitationResponse, MemberStatus
from app.models.projects import MilestoneStatus
from app.services.team import (
    MAX_LEAD_CHANGE_REQUESTS_PER_WEEK,
    MAX_PENDING_INVITATIONS,
    invitation_state,
    member_inactive_days,
    milestone_may_activate,
    slots_filled,
)

pytestmark = pytest.mark.unit
NOW = datetime(2026, 11, 24, 6, tzinfo=UTC)


def inv(**kw: Any) -> Any:
    base = {"sent_at": NOW - timedelta(hours=1), "expires_at": NOW + timedelta(hours=47),
            "response": None, "responded_at": None}  # fmt: skip
    return SimpleNamespace(**{**base, **kw})


def test_invitation_states() -> None:
    assert invitation_state(None, NOW) == "CLOSED"
    assert invitation_state(inv(sent_at=None, expires_at=None), NOW) == "UNSENT"
    assert invitation_state(inv(), NOW) == "PENDING"
    assert invitation_state(inv(expires_at=NOW), NOW) == "EXPIRED"  # at the instant: expired
    assert invitation_state(inv(expires_at=NOW + timedelta(seconds=1)), NOW) == "PENDING"
    assert invitation_state(inv(response=InvitationResponse.ACCEPTED), NOW) == "ACCEPTED"
    assert invitation_state(inv(response=InvitationResponse.DECLINED), NOW) == "DECLINED"


def test_places_still_waiting_for_an_accepted_member() -> None:
    s1, s2 = SimpleNamespace(id=uuid.uuid4(), count=2), SimpleNamespace(id=uuid.uuid4(), count=1)
    m = lambda slot, status: SimpleNamespace(slot_id=slot.id, status=status)  # noqa: E731
    members = [m(s1, MemberStatus.ACTIVE), m(s1, MemberStatus.INVITED), m(s2, MemberStatus.ACTIVE)]
    assert slots_filled([s1, s2], members) == [s1]  # type: ignore[arg-type]
    members[1] = m(s1, MemberStatus.ACTIVE)
    assert slots_filled([s1, s2], members) == []  # type: ignore[arg-type]
    members.append(m(s2, MemberStatus.DECLINED))
    assert slots_filled([s1, s2], members) == []  # type: ignore[arg-type]


def test_only_planned_roots_activate_at_start() -> None:
    planned = SimpleNamespace(status=MilestoneStatus.PLANNED)
    assert milestone_may_activate(planned, set()) is True  # type: ignore[arg-type]
    assert milestone_may_activate(planned, {uuid.uuid4()}) is False  # type: ignore[arg-type]
    active = SimpleNamespace(status=MilestoneStatus.ACTIVE)
    assert milestone_may_activate(active, set()) is False  # type: ignore[arg-type]


def test_no_activity_signal_until_phase_9() -> None:
    assert asyncio.run(member_inactive_days(None, None)) is None  # type: ignore[arg-type]


def test_abuse_caps() -> None:
    assert (MAX_PENDING_INVITATIONS, MAX_LEAD_CHANGE_REQUESTS_PER_WEEK) == (10, 3)
