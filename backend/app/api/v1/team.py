"""Team endpoints (spec §10.2 Team; DECISIONS D118–D138): invitations, the lead, starting the
project, team repair, leaving and removal.

Object checks are in the services and answer 404 for anything that isn't the caller's (§14.5);
`GET /projects/{id}/team` is role-shaped (D130). Writes that change the project take
`If-Match: <project version>`; a stale one is 409 `VERSION_CONFLICT`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.api.deps import acting
from app.schemas.common import error_responses
from app.schemas.repair import EX_REPAIR, ChooseIn, RaiseBudgetIn, RepairOut
from app.schemas.team import (
    EX_ACTION,
    EX_CLIENT_TEAMS,
    EX_MY_INVITATIONS,
    EX_TEAM_CLIENT,
    ActionOut,
    ChooseLeadIn,
    ClientTeamCard,
    DecisionIn,
    DeclineIn,
    LeadChangeRequestIn,
    LeadChangeRequestOut,
    LeaveIn,
    MyInvitationsOut,
    RemovalRequestIn,
    RemovalRequestOut,
    TeamForClient,
    TeamForMember,
)
from app.services import repair as repair_svc
from app.services import team as svc
from app.services.context import Ctx

router = APIRouter(tags=["team"])

Invitee = Annotated[Ctx, Depends(acting("invitation.respond"))]
Reader = Annotated[Ctx, Depends(acting("team.read"))]
Lister = Annotated[Ctx, Depends(acting("team.list"))]
Chooser = Annotated[Ctx, Depends(acting("team.lead.choose"))]
Decider = Annotated[Ctx, Depends(acting("team.lead.decide"))]
Lead = Annotated[Ctx, Depends(acting("team.lead.decline"))]
Requester = Annotated[Ctx, Depends(acting("team.lead.request"))]
Leaver = Annotated[Ctx, Depends(acting("team.leave"))]
Remover = Annotated[Ctx, Depends(acting("team.removal.request"))]
RepairReader = Annotated[Ctx, Depends(acting("team.repair"))]
RepairWriter = Annotated[Ctx, Depends(acting("team.repair.choose"))]
Starter = Annotated[Ctx, Depends(acting("project.start"))]
Admin = Annotated[Ctx, Depends(acting("admin.access"))]
IfMatch = Annotated[
    int | None, Header(alias="If-Match", ge=0, le=2_147_483_647, description="Project version")
]


def _ok(example: object, *errors: int) -> dict[int | str, dict[str, object]]:
    ok: dict[int | str, dict[str, object]] = {
        200: {"content": {"application/json": {"example": example}}}
    }
    return {**ok, **error_responses(*errors)}


ACTION = _ok(EX_ACTION, 401, 403, 404, 409, 422, 429)


@router.get(
    "/projects/{project_id}/team",
    summary="The project's team",
    response_model=TeamForClient | TeamForMember,
    responses=_ok(EX_TEAM_CLIENT, 401, 403, 404, 422, 429),
)
async def get_team(project_id: uuid.UUID, ctx: Reader) -> TeamForClient | TeamForMember:
    """Members and invitations, the lead and its recommendation, start readiness, lead-change and
    removal requests and the repair status. The client and admins see every member's price and
    days; a member sees teammates without them and only their own requests (D130)."""
    return await svc.get_team(ctx, project_id)


@router.post(
    "/invitations/{invitation_id}/accept",
    summary="Accept an invitation",
    response_model=ActionOut,
    responses=ACTION,
)
async def accept(invitation_id: uuid.UUID, ctx: Invitee) -> ActionOut:
    """Join the team. Refused (409 `UNAVAILABLE`) when your free hours a week can't cover it."""
    return await svc.accept(ctx, invitation_id)


@router.post(
    "/invitations/{invitation_id}/decline",
    summary="Decline an invitation",
    response_model=ActionOut,
    responses=ACTION,
)
async def decline(invitation_id: uuid.UUID, body: DeclineIn, ctx: Invitee) -> ActionOut:
    """Say no (an optional reason, up to 500 characters). The client is told and DevSync looks
    for a replacement."""
    return await svc.decline(ctx, invitation_id, body)


@router.post(
    "/projects/{project_id}/team/lead",
    summary="Choose the team lead",
    response_model=ActionOut,
    responses=ACTION,
)
async def choose_lead(
    project_id: uuid.UUID, body: ChooseLeadIn, ctx: Chooser, if_match: IfMatch = None
) -> ActionOut:
    """Any developer who accepted and hasn't declined the role; once every place is accepted
    before the start, at any time after it (with a reason)."""
    return await svc.choose_lead(ctx, project_id, body, if_match)


@router.post(
    "/projects/{project_id}/team/lead/decline",
    summary="Decline the lead role",
    response_model=ActionOut,
    responses=ACTION,
)
async def decline_lead(project_id: uuid.UUID, ctx: Lead) -> ActionOut:
    """The lead gives up the role, not the team; the client chooses the next lead."""
    return await svc.decline_lead(ctx, project_id)


@router.post(
    "/projects/{project_id}/lead-change-requests",
    summary="Ask for a lead change",
    status_code=201,
    response_model=LeadChangeRequestOut,
    responses=error_responses(401, 403, 404, 409, 422, 429),
)
async def request_lead_change(
    project_id: uuid.UUID, body: LeadChangeRequestIn, ctx: Requester
) -> LeadChangeRequestOut:
    """An active member, with a reason (20–500 characters); one open request at a time and at
    most three a week."""
    return await svc.request_lead_change(ctx, project_id, body)


@router.post(
    "/lead-change-requests/{request_id}/approve",
    summary="Approve a lead change",
    response_model=ActionOut,
    responses=ACTION,
)
async def approve_lead_change(request_id: uuid.UUID, ctx: Decider) -> ActionOut:
    """The current lead becomes a normal member; choose the next lead from the recommendation."""
    return await svc.decide_lead_change(ctx, request_id, approve=True, reason=None)


@router.post(
    "/lead-change-requests/{request_id}/reject",
    summary="Reject a lead change",
    response_model=ActionOut,
    responses=ACTION,
)
async def reject_lead_change(request_id: uuid.UUID, body: DecisionIn, ctx: Decider) -> ActionOut:
    """With a reason the requester sees."""
    return await svc.decide_lead_change(ctx, request_id, approve=False, reason=body.reason)


@router.post(
    "/lead-change-requests/{request_id}/withdraw",
    summary="Withdraw your lead-change request",
    response_model=ActionOut,
    responses=ACTION,
)
async def withdraw_lead_change(request_id: uuid.UUID, ctx: Requester) -> ActionOut:
    return await svc.withdraw_lead_change(ctx, request_id)


@router.post(
    "/projects/{project_id}/start",
    summary="Start the project",
    response_model=ActionOut,
    responses=ACTION,
)
async def start(project_id: uuid.UUID, ctx: Starter, if_match: IfMatch = None) -> ActionOut:
    """Once every place is accepted and a lead chosen: the project starts today (or on its planned
    date if later), the first milestones activate and the workspace opens (D118, D119)."""
    return await svc.start_project(ctx, project_id, if_match)


@router.get(
    "/projects/{project_id}/repair",
    summary="Team repair proposal",
    response_model=RepairOut,
    responses=_ok(EX_REPAIR, 401, 403, 404, 422, 429),
)
async def get_repair(project_id: uuid.UUID, ctx: RepairReader) -> RepairOut:
    """The latest proposal: ranked candidates with their project impact, or why there are none."""
    return await repair_svc.get_repair(ctx, project_id)


@router.post(
    "/repair-proposals/{proposal_id}/choose",
    summary="Invite a replacement",
    response_model=RepairOut,
    responses=_ok(EX_REPAIR, 401, 403, 404, 409, 422, 429),
)
async def choose_replacement(
    proposal_id: uuid.UUID, body: ChooseIn, ctx: RepairWriter
) -> RepairOut:
    return await repair_svc.choose(ctx, proposal_id, body)


@router.post(
    "/projects/{project_id}/slots/{slot_id}/reopen",
    summary="Reopen a place for 48 hours",
    response_model=RepairOut,
    responses=_ok(EX_REPAIR, 401, 403, 404, 409, 422, 429),
)
async def reopen_slot(project_id: uuid.UUID, slot_id: uuid.UUID, ctx: RepairWriter) -> RepairOut:
    """Only when repair found nobody for the place; at most twice per place."""
    return await repair_svc.reopen_slot(ctx, project_id, slot_id)


@router.post(
    "/projects/{project_id}/budget",
    summary="Raise the budget",
    response_model=RepairOut,
    responses=_ok(EX_REPAIR, 401, 403, 404, 409, 422, 429),
)
async def raise_budget(
    project_id: uuid.UUID, body: RaiseBudgetIn, ctx: RepairWriter, if_match: IfMatch = None
) -> RepairOut:
    """Only when repair says the budget left is too low; by at least the shortfall."""
    return await repair_svc.raise_budget(ctx, project_id, body, if_match)


@router.post(
    "/team-members/{member_id}/leave",
    summary="Leave the project",
    response_model=ActionOut,
    responses=ACTION,
)
async def leave(member_id: uuid.UUID, body: LeaveIn, ctx: Leaver) -> ActionOut:
    return await svc.leave(ctx, member_id, body)


@router.post(
    "/team-members/{member_id}/removal-requests",
    summary="Ask an admin to remove a member",
    status_code=201,
    response_model=RemovalRequestOut,
    responses=error_responses(401, 403, 404, 409, 422, 429),
)
async def request_removal(
    member_id: uuid.UUID, body: RemovalRequestIn, ctx: Remover
) -> RemovalRequestOut:
    """Needs a basis: 10 days without activity (tracked from Phase 9) or a dispute (Phase 12)."""
    return await svc.request_removal(ctx, member_id, body)


@router.get(
    "/me/invitations",
    summary="My invitations and teams",
    response_model=MyInvitationsOut,
    responses=_ok(EX_MY_INVITATIONS, 401, 403, 422, 429),
)
async def my_invitations(ctx: Invitee) -> MyInvitationsOut:
    return await svc.my_invitations(ctx)


@router.get(
    "/me/teams",
    summary="My projects' teams",
    response_model=list[ClientTeamCard],
    responses=_ok(EX_CLIENT_TEAMS, 401, 403, 422, 429),
)
async def my_teams(ctx: Lister) -> list[ClientTeamCard]:
    return await svc.client_teams(ctx)


@router.get(
    "/admin/removal-requests",
    summary="Member removal requests (admin)",
    response_model=list[RemovalRequestOut],
    responses=error_responses(401, 403, 404, 422, 429),
)
async def admin_removals(ctx: Admin) -> list[RemovalRequestOut]:
    return await svc.admin_removals(ctx)


@router.post(
    "/admin/removal-requests/{request_id}/approve",
    summary="Approve a member removal (admin, step-up)",
    response_model=ActionOut,
    responses=ACTION,
)
async def approve_removal(request_id: uuid.UUID, body: DecisionIn, ctx: Admin) -> ActionOut:
    return await svc.decide_removal(ctx, request_id, approve=True, reason=body.reason)


@router.post(
    "/admin/removal-requests/{request_id}/reject",
    summary="Reject a member removal (admin, step-up)",
    response_model=ActionOut,
    responses=ACTION,
)
async def reject_removal(request_id: uuid.UUID, body: DecisionIn, ctx: Admin) -> ActionOut:
    return await svc.decide_removal(ctx, request_id, approve=False, reason=body.reason)
