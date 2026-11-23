"""Lead recommendation (spec §1.6 rule 1; D131, D132): maximal X_m among ACTIVE members, each
tie-break on its own, decliners and excluded members skipped, newcomers on the same footing, and
the reason text."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.algorithms.lead import LeadCandidate, rank, reason, recommend_lead, score100

pytestmark = pytest.mark.unit
T0 = datetime(2026, 11, 24, 6, tzinfo=UTC)


def m(
    mid: str, xm: float = 0.6, done: int = 3, c: float = 0.6, at: int = 0, **kw: object
) -> LeadCandidate:
    return LeadCandidate(member_id=mid, developer_id=f"d-{mid}", active=kw.pop("active", True),  # type: ignore[arg-type]
                         xm=xm, completed_projects=done, competency=c,
                         responded_at=T0 + timedelta(hours=at), **kw)  # type: ignore[arg-type]  # fmt: skip


def test_highest_teamwork_wins() -> None:
    rec = recommend_lead([m("a", xm=0.7), m("b", xm=0.86), m("c", xm=0.5)])
    assert rec is not None
    assert rec.member_id == "b"
    assert rec.ranking == ("b", "a", "c")
    assert rec.reason == "Highest teamwork capacity: 86"


def test_tie_on_teamwork_goes_to_more_completed_projects() -> None:
    assert recommend_lead([m("a", done=2), m("b", done=5)]).member_id == "b"  # type: ignore[union-attr]


def test_then_higher_competency() -> None:
    assert recommend_lead([m("a", c=0.7), m("b", c=0.8)]).member_id == "b"  # type: ignore[union-attr]


def test_then_earlier_acceptance() -> None:
    assert recommend_lead([m("a", at=5), m("b", at=1)]).member_id == "b"  # type: ignore[union-attr]


def test_then_developer_id_as_the_final_key() -> None:
    assert recommend_lead([m("b"), m("a")]).member_id == "a"  # type: ignore[union-attr]


def test_a_newcomer_without_a_snapshot_ranks_on_starting_values() -> None:
    """The service passes the computed §9.1.3 values; a newcomer with 0 projects can win on X_m."""
    newcomer = m("n", xm=0.9, done=0, c=0.3)
    assert recommend_lead([m("a", xm=0.6, done=8), newcomer]).member_id == "n"  # type: ignore[union-attr]


def test_only_active_members_are_considered() -> None:
    rec = recommend_lead([m("a", xm=0.95, active=False), m("b", xm=0.5)])
    assert rec is not None
    assert rec.member_id == "b"
    assert recommend_lead([m("a", active=False)]) is None
    assert recommend_lead([]) is None


def test_the_next_member_skips_everyone_who_declined_the_role() -> None:
    team = [m("a", xm=0.9, declined_lead=True), m("b", xm=0.8, declined_lead=True), m("c", xm=0.7)]
    rec = recommend_lead(team)
    assert rec is not None
    assert rec.member_id == "c"
    assert rec.reason == "Highest teamwork capacity of the members available: 70"
    assert recommend_lead([m("a", declined_lead=True)]) is None


def test_an_excluded_outgoing_lead_is_skipped() -> None:
    rec = recommend_lead([m("a", xm=0.9), m("b", xm=0.8)], exclude=["a"])
    assert rec is not None
    assert rec.member_id == "b"
    assert "available" in rec.reason


def test_reason_text_and_led_teams_clause() -> None:
    assert (
        reason(m("a", xm=0.855, led_teams=2)) == "Highest teamwork capacity: 86; led 2 past teams"
    )
    assert reason(m("a", xm=0.86, led_teams=1)) == "Highest teamwork capacity: 86; led 1 past team"
    assert reason(m("a", xm=0.86)) == "Highest teamwork capacity: 86"
    assert (score100(0.005), score100(0.004), score100(1.2), score100(-1)) == (1, 0, 100, 0)


members = st.lists(
    st.builds(
        LeadCandidate,
        member_id=st.uuids().map(str),
        developer_id=st.uuids().map(str),
        active=st.booleans(),
        xm=st.floats(0, 1),
        completed_projects=st.integers(0, 20),
        competency=st.floats(0, 1),
        responded_at=st.datetimes(
            min_value=datetime(2026, 1, 1), max_value=datetime(2027, 1, 1), timezones=st.just(UTC)
        ),
        declined_lead=st.booleans(),
    ),
    max_size=8,
    unique_by=lambda c: c.member_id,
)


@settings(max_examples=200, deadline=None)
@given(members)
def test_the_recommendation_always_has_maximal_teamwork(team: list[LeadCandidate]) -> None:
    eligible = [c for c in team if c.active and not c.declined_lead]
    rec = recommend_lead(team)
    if not eligible:
        assert rec is None
        return
    assert rec is not None
    chosen = next(c for c in team if c.member_id == rec.member_id)
    assert chosen.xm == max(c.xm for c in eligible)
    assert list(rec.ranking) == [c.member_id for c in rank(team)]
