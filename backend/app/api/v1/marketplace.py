"""Marketplace: search and recommended projects (spec §10 Marketplace, §9.16).

Developer-only; read-only; no bid data is ever returned (sealed bids, §14.5). Filters are
whitelisted (unknown query params → 422 from FastAPI); the free-text query goes through
`plainto_tsquery` server-side (§14.7).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import acting
from app.schemas.common import Page, error_responses
from app.schemas.marketplace import ProjectCard, RecommendedProject
from app.services import marketplace as svc
from app.services.context import Ctx

router = APIRouter(tags=["marketplace"])

Reader = Annotated[Ctx, Depends(acting("marketplace.read"))]

EX_CARD = {
    "id": "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c",
    "title": "Online ordering system",
    "summary": "A web app for a restaurant to take and track orders.",
    "status": "BIDDING",
    "budget_paisa": 12_000_000,
    "deadline_days": 30,
    "team_size": 4,
    "bidding_deadline": "2026-10-31T18:00:00Z",
    "skills": ["FastAPI", "PostgreSQL", "React", "Testing"],
    "created_at": "2026-10-20T06:00:00Z",
}


@router.get(
    "/projects/search",
    summary="Search open projects",
    response_model=Page[ProjectCard],
    responses={
        200: {
            "content": {"application/json": {"example": {"items": [EX_CARD], "next_cursor": None}}}
        },
        **error_responses(401, 403, 404, 422),
    },
)
async def search_projects(
    ctx: Reader,
    *,
    q: Annotated[str | None, Query(max_length=200)] = None,
    skills: Annotated[list[str] | None, Query()] = None,
    budget_min: Annotated[int | None, Query(ge=0)] = None,
    budget_max: Annotated[int | None, Query(ge=0)] = None,
    deadline_max: Annotated[int | None, Query(ge=1, le=365)] = None,
    team_size: Annotated[int | None, Query(ge=2, le=10)] = None,
    sort: Annotated[str, Query()] = "newest",
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ProjectCard]:
    return await svc.search(
        ctx.db,
        q=q,
        skills=skills,
        budget_min=budget_min,
        budget_max=budget_max,
        deadline_max=deadline_max,
        team_size=team_size,
        sort=sort,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/projects/recommended",
    summary="Projects recommended for me",
    response_model=list[RecommendedProject],
    responses={
        200: {
            "content": {
                "application/json": {"example": [{"project": EX_CARD, "skill_match_count": 2}]}
            }
        },
        **error_responses(401, 403, 404),
    },
)
async def recommended_projects(ctx: Reader) -> list[RecommendedProject]:
    return await svc.recommended(ctx.db, ctx.uid)
