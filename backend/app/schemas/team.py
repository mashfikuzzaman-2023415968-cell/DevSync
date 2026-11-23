"""Team API schemas (spec §10.2 Team, §13.5 #9/#25/#33; DECISIONS D121–D134).

Role-shaped (§14.5, D130): the client (and admins) get `TeamForClient` with every member's price
and days; a member gets `TeamForMember`, where other members carry no `price_paisa` or
`days_needed` and only their own lead-change requests appear. Scores are 0–1 here (the UI shows
0–100); money is integer paisa; times are UTC.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import StrictRequest

MemberStatusOut = Literal[
    "INVITED", "ACTIVE", "DECLINED", "EXPIRED", "COMPLETED", "LEFT", "REMOVED"
]
InvitationState = Literal["UNSENT", "PENDING", "ACCEPTED", "DECLINED", "EXPIRED", "CLOSED"]
Reason = Field(min_length=20, max_length=500)


class InvitationOut(BaseModel):
    id: uuid.UUID
    state: InvitationState
    sent_at: datetime | None
    expires_at: datetime | None
    responded_at: datetime | None
    is_replacement: bool


class TeamMemberForMember(BaseModel):
    """A member as another member sees them: no price, no days (sealed among members, D130)."""

    id: uuid.UUID
    developer_id: uuid.UUID
    developer_name: str
    slot_id: uuid.UUID
    slot_label: str
    status: MemberStatusOut
    is_lead: bool
    is_newcomer: bool
    competency: float
    teamwork: float
    hours_per_week: int
    joined_at: datetime | None
    invitation: InvitationOut | None
    is_you: bool


class TeamMemberForClient(TeamMemberForMember):
    price_paisa: int
    days_needed: int
    left_reason: str | None
    lead_declined: bool
    fully_booked: bool  # D124: their accept would be refused for lack of free hours now


class LeadRecommendationOut(BaseModel):
    member_id: uuid.UUID
    developer_name: str
    reason: str
    preselected_member_id: uuid.UUID | None  # a suggested member from an approved request


class LeadChangeRequestOut(BaseModel):
    id: uuid.UUID
    requested_by: uuid.UUID
    requester_name: str
    reason: str
    suggested_member_id: uuid.UUID | None
    status: Literal["PENDING", "APPROVED", "REJECTED", "WITHDRAWN"]
    decision_reason: str | None
    created_at: datetime
    decided_at: datetime | None


class RemovalRequestOut(BaseModel):
    id: uuid.UUID
    team_member_id: uuid.UUID
    member_name: str
    reason: str
    basis: Literal["INACTIVITY", "DISPUTE"]
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    decision_reason: str | None
    created_at: datetime


class RepairSummaryOut(BaseModel):
    id: uuid.UUID
    status: Literal["COMPUTING", "READY", "NO_CANDIDATES", "CHOSEN", "SUPERSEDED", "CANCELLED"]
    departed_member_id: uuid.UUID
    job_id: uuid.UUID | None
    created_at: datetime


class _TeamBase(BaseModel):
    project_id: uuid.UUID
    project_title: str
    project_status: str
    project_version: int
    team_id: uuid.UUID
    team_status: Literal["PENDING", "ACTIVE", "COMPLETED", "CANCELLED"]
    lead_member_id: uuid.UUID | None


class TeamForMember(_TeamBase):
    view: Literal["member"] = "member"
    members: list[TeamMemberForMember]
    my_member_id: uuid.UUID
    lead_change_requests: list[LeadChangeRequestOut]  # your own only


class TeamForClient(_TeamBase):
    view: Literal["client"] = "client"
    members: list[TeamMemberForClient]
    recommendation: LeadRecommendationOut | None
    can_choose_lead: bool
    can_start: bool
    start_blockers: list[str]  # plain sentences: why "Start project" is disabled
    lead_change_requests: list[LeadChangeRequestOut]
    removal_requests: list[RemovalRequestOut]
    repair: RepairSummaryOut | None


# ------------------------------------------------------------------------------- requests


class DeclineIn(StrictRequest):
    reason: str | None = Field(default=None, max_length=500)


class ChooseLeadIn(StrictRequest):
    member_id: uuid.UUID
    reason: str | None = Field(default=None, min_length=20, max_length=500)  # needed after start


class LeadChangeRequestIn(StrictRequest):
    reason: str = Reason
    suggested_member_id: uuid.UUID | None = None


class DecisionIn(StrictRequest):
    reason: str = Reason


class LeaveIn(StrictRequest):
    reason: str = Reason


class RemovalRequestIn(StrictRequest):
    reason: str = Reason
    basis: Literal["INACTIVITY", "DISPUTE"]


# ------------------------------------------------------------------------------ my views


class MyInvitationOut(BaseModel):
    """An invitation on the developer's dashboard (screen 9)."""

    id: uuid.UUID
    member_id: uuid.UUID
    project_id: uuid.UUID
    project_title: str
    slot_label: str
    price_paisa: int  # your own bid
    days_needed: int
    state: InvitationState
    sent_at: datetime | None
    expires_at: datetime | None
    responded_at: datetime | None
    is_replacement: bool


class MyMembershipOut(BaseModel):
    member_id: uuid.UUID
    project_id: uuid.UUID
    project_title: str
    project_status: str
    status: MemberStatusOut
    is_lead: bool


class MyInvitationsOut(BaseModel):
    invitations: list[MyInvitationOut]  # pending, and answered in the last 30 days
    memberships: list[MyMembershipOut]  # where you are INVITED or ACTIVE


class ClientTeamCard(BaseModel):
    """One card of `/client/teams`."""

    project_id: uuid.UUID
    project_title: str
    project_status: str
    team_id: uuid.UUID
    team_status: str
    accepted: int
    places: int
    lead_name: str | None
    needs_attention: list[str]  # REPAIR_OPEN, INVITATION_EXPIRING, FULLY_BOOKED, CHOOSE_LEAD


class ActionOut(BaseModel):
    """The state after an action, for the screen to refresh."""

    status: str
    message: str


_PID = "6a1d3c8f-4e5b-4f9c-8d2e-3b4c5d6e7f80"
_TID = "7b2e4d90-5f6c-4a0d-9e3f-4c5d6e7f8091"
_M1 = "8c3f5ea1-6a7d-4b1e-8f40-5d6e7f8091a2"
_INV = {
    "id": "9d40a6b2-7b8e-4c2f-9a51-6e7f8091a2b3",
    "state": "PENDING",
    "sent_at": "2026-11-24T06:00:00Z",
    "expires_at": "2026-11-26T06:00:00Z",
    "responded_at": None,
    "is_replacement": False,
}
_MEMBER = {
    "id": _M1,
    "developer_id": "a0e1b7c3-8c9f-4d30-8b62-7f8091a2b3c4",
    "developer_name": "Nusrat Jahan",
    "slot_id": "b1f2c8d4-9d0a-4e41-9c73-8091a2b3c4d5",
    "slot_label": "React developer",
    "status": "ACTIVE",
    "is_lead": False,
    "is_newcomer": False,
    "competency": 0.74,
    "teamwork": 0.66,
    "hours_per_week": 20,
    "joined_at": "2026-11-24T07:00:00Z",
    "invitation": {**_INV, "state": "ACCEPTED", "responded_at": "2026-11-24T07:00:00Z"},
    "is_you": False,
}
EX_TEAM_CLIENT = {
    "project_id": _PID,
    "project_title": "Online ordering system",
    "project_status": "TEAM_PENDING",
    "project_version": 4,
    "team_id": _TID,
    "team_status": "PENDING",
    "lead_member_id": None,
    "view": "client",
    "members": [{**_MEMBER, "price_paisa": 2_400_000, "days_needed": 22, "left_reason": None,
                 "lead_declined": False, "fully_booked": False}],
    "recommendation": {"member_id": _M1, "developer_name": "Nusrat Jahan",
                       "reason": "Highest teamwork capacity: 66", "preselected_member_id": None},
    "can_choose_lead": True,
    "can_start": False,
    "start_blockers": ["Choose a team lead."],
    "lead_change_requests": [],
    "removal_requests": [],
    "repair": None,
}  # fmt: skip
EX_TEAM_MEMBER = {
    **{k: v for k, v in EX_TEAM_CLIENT.items() if k in _TeamBase.model_fields},
    "view": "member",
    "members": [_MEMBER],
    "my_member_id": _M1,
    "lead_change_requests": [],
}
EX_ACTION = {"status": "ACTIVE", "message": "You joined the team."}
EX_MY_INVITATIONS = {
    "invitations": [
        {
            **_INV,
            "member_id": _M1,
            "project_id": _PID,
            "project_title": "Online ordering system",
            "slot_label": "React developer",
            "price_paisa": 2_400_000,
            "days_needed": 22,
        }
    ],
    "memberships": [],
}
EX_CLIENT_TEAMS = [
    {
        "project_id": _PID,
        "project_title": "Online ordering system",
        "project_status": "TEAM_PENDING",
        "team_id": _TID,
        "team_status": "PENDING",
        "accepted": 3,
        "places": 4,
        "lead_name": None,
        "needs_attention": ["REPAIR_OPEN"],
    }
]
