"""Reputation API schemas (spec §10.2 Reputation, §13.5 #16; contract-first §10.4).

Scores are 0–1 decimals with 3 places, serialised as strings (like `ReputationSummary`, D58);
the UI shows them as whole numbers 0–100. Parameter keys are the model's (`omega`, `x`, `xm`,
`beta`, `mu`, `t`); the plain labels (Expertise, Communication, …) are the UI's.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

ParameterName = Literal["omega", "x", "xm", "beta", "mu", "t", "c", "p"]


class ReputationParameters(BaseModel):
    """The six [PCS] parameters (§9.1): expertise ω, communication X, teamwork X_m, quality β,
    client diversity μ, punctuality T. Null only for another user's newcomer without a record."""

    omega: Decimal | None
    x: Decimal | None
    xm: Decimal | None
    beta: Decimal | None
    mu: Decimal | None
    t: Decimal | None


class SkillCompetency(BaseModel):
    """Per-skill competency C_{i,s} (§9.1.7), 0–1."""

    skill_id: uuid.UUID
    name: str
    competency: Decimal


class NewcomerBasis(BaseModel):
    """Where a newcomer's starting values come from (§9.1.3). Only ever shown to the developer
    themself: the verified items describe their own account."""

    verified_items: int = Field(
        ge=0, le=4, description="phone, email, complete profile, verified certificate"
    )
    evidence_domains: int = Field(ge=0, le=8, description="domains with a passing skill result")
    review_default: Decimal = Field(description="quality (β) used until the first client rating")
    threshold: int = Field(description="completed projects after which they are not a newcomer")


class DeveloperReputation(BaseModel):
    """A developer's reputation as the caller may see it (§13.5 #16; GET
    /developers/{id}/reputation)."""

    developer_id: uuid.UUID
    parameters: ReputationParameters
    competency: Decimal | None
    performance: Decimal | None
    completed_projects: int
    distinct_clients: int
    is_newcomer: bool
    seeded: bool = Field(description="a fixed demo value (D48); never true in production")
    simulated: bool = Field(description="computed from simulated project histories (D84)")
    skills: list[SkillCompetency]
    newcomer: NewcomerBasis | None = Field(
        description="the developer's own newcomer starting values; null for anyone else"
    )
    updated_at: datetime | None


class ReputationChange(BaseModel):
    """One parameter's change after one project, with a plain-language reason."""

    parameter: ParameterName
    old: Decimal
    new: Decimal
    raw_new: Decimal = Field(description="before the per-project change limit")
    capped: bool
    reason: str


class ReputationHistoryItem(BaseModel):
    """What one completed project changed (`/me/reputation/history`), newest project first."""

    history_id: uuid.UUID
    project_label: str
    domain: str
    completed_at: datetime
    simulated: bool
    changes: list[ReputationChange]


EX_REPUTATION = {
    "developer_id": "7b0c2a4e-9d61-4b52-8f0a-3a1d5e6c7b80",
    "parameters": {"omega": "0.786", "x": "0.860", "xm": "0.686", "beta": "0.748",
                   "mu": "0.857", "t": "0.549"},
    "competency": "0.808",
    "performance": "0.726",
    "completed_projects": 8,
    "distinct_clients": 5,
    "is_newcomer": False,
    "seeded": False,
    "simulated": True,
    "skills": [{"skill_id": "3f6a1c2e-5b7d-4e8f-9a0b-1c2d3e4f5a6b", "name": "React",
                "competency": "0.433"}],
    "newcomer": None,
    "updated_at": "2026-11-21T09:00:00Z",
}  # fmt: skip

EX_HISTORY_ITEM = {
    "history_id": "5d2e8f1a-0b3c-4d5e-9f6a-7b8c9d0e1f2a",
    "project_label": "Clinic booking site",
    "domain": "FRONTEND",
    "completed_at": "2025-02-08T06:00:00Z",
    "simulated": True,
    "changes": [
        {"parameter": "t", "old": "0.500", "new": "0.333", "raw_new": "0.333", "capped": False,
         "reason": "Punctuality 50 → 33: finished in 20 of 30 days."},
        {"parameter": "x", "old": "0.550", "new": "0.700", "raw_new": "0.725", "capped": True,
         "reason": "Communication 55 → 70: communication on this project was rated 80. The "
                   "change was limited to 15 points per project (it would have been 73)."},
    ],
}  # fmt: skip
