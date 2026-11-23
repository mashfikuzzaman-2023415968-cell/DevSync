"""Team repair API schemas (spec §9.9, §10.2 Team; D126–D128, D138). Client and admins only:
developers never see candidate lists (sealed bids)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import StrictRequest


class Impact(BaseModel):
    """What the candidate does to the project (D138)."""

    affected_milestones: list[str]  # names
    baseline_days: int
    new_days: int
    delay_days: int
    budget_delta_paisa: int  # team price with the candidate − budget after fee (> 0: over)
    budget_only: bool


class RepairCandidate(BaseModel):
    bid_id: uuid.UUID
    developer_name: str
    is_newcomer: bool
    competency: float
    teamwork: float
    price_paisa: int
    days_needed: int
    fitness: float
    team_price_paisa: int
    impact: Impact


class RepairReason(BaseModel):
    code: Literal["NO_BIDS_FOR_SLOT", "REMAINING_BUDGET_TOO_LOW", "NONE_AVAILABLE",
                  "NEWCOMER_MINIMUM_RELAXED"]  # fmt: skip
    message: str
    shortfall_paisa: int | None = None


class RepairOut(BaseModel):
    id: uuid.UUID
    status: Literal["COMPUTING", "READY", "NO_CANDIDATES", "CHOSEN", "SUPERSEDED", "CANCELLED"]
    job_id: uuid.UUID | None
    created_at: datetime
    departed_member_id: uuid.UUID
    slot_id: uuid.UUID | None
    slot_label: str
    candidates: list[RepairCandidate]
    reasons: list[RepairReason]
    impact: dict[str, object] | None
    chosen_bid_id: uuid.UUID | None


class ChooseIn(StrictRequest):
    bid_id: uuid.UUID


class RaiseBudgetIn(StrictRequest):
    budget_paisa: int = Field(gt=0, le=10_000_000_000)


EX_REPAIR = {
    "id": "5f0c2b7e-3d4a-4e8b-9c1d-2a3b4c5d6e7f",
    "status": "READY",
    "job_id": "0b7c1a52-8d1e-4f55-9a3e-2f1c6f2d9b10",
    "created_at": "2026-11-25T06:00:00Z",
    "departed_member_id": "8c3f5ea1-6a7d-4b1e-8f40-5d6e7f8091a2",
    "slot_id": "b1f2c8d4-9d0a-4e41-9c73-8091a2b3c4d5",
    "slot_label": "Testing developer",
    "candidates": [
        {
            "bid_id": "9d40a6b2-7b8e-4c2f-9a51-6e7f8091a2b3",
            "developer_name": "Zahid Mahmud",
            "is_newcomer": False,
            "competency": 0.55,
            "teamwork": 0.6,
            "price_paisa": 1_900_000,
            "days_needed": 22,
            "fitness": 0.7412,
            "team_price_paisa": 9_100_000,
            "impact": {
                "affected_milestones": ["Testing & launch"],
                "baseline_days": 24,
                "new_days": 25,
                "delay_days": 1,
                "budget_delta_paisa": -1_700_000,
                "budget_only": False,
            },
        }
    ],
    "reasons": [],
    "impact": {"departed": "Testing developer"},
    "chosen_bid_id": None,
}
