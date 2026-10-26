"""Bid versions, INELIGIBLE marking, the developer's bid list index and settings v4 (Phase 5 gaps).

- `bids.version` (optimistic concurrency, spec §10.1: edits send `If-Match`, a stale one is 409
  `VERSION_CONFLICT`) and `bids.evaluated_at` (when bidding closed and Algorithm 1 marked the
  bid ACTIVE or INELIGIBLE, spec §8; `ineligible_reasons` already exists).
- One *standing* bid per developer and project: the partial unique index now covers ACTIVE and
  INELIGIBLE (an INELIGIBLE bid can become ACTIVE again when the client lowers the standards or
  extends bidding), WITHDRAWN rows are still kept (D49).
- `(developer_id, created_at, id)` for the keyset pagination of `GET /me/bids`.
- Settings v4: `captcha.max_number`, the ALTCHA difficulty (§14.16 "difficulty from settings").

Revision ID: 0009_bid_rules
Revises: 0008_public_best_score
Create Date: 2026-10-24 00:00:00.000000+00:00
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_bid_rules"
down_revision: str | None = "0008_public_best_score"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_V4 = Path(__file__).resolve().parent.parent / "seed" / "platform_settings_v4.json"


def upgrade() -> None:
    op.add_column("bids", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("bids", sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_index("one_active_bid_per_developer", table_name="bids")
    op.create_index(
        "one_standing_bid_per_developer",
        "bids",
        ["project_id", "developer_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('ACTIVE', 'INELIGIBLE')"),  # forbidden-ok: DDL
    )
    op.create_index(
        "ix_bids_developer_created", "bids", ["developer_id", "created_at", "id"], unique=False
    )
    settings_table = sa.table(
        "platform_settings",
        sa.column("version", sa.Integer()),
        sa.column("values", postgresql.JSONB()),
        sa.column("reason", sa.Text()),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "version": 4,
                "values": json.loads(SEED_V4.read_text(encoding="utf-8")),
                "reason": "CAPTCHA difficulty as a setting (captcha.max_number)",
            }
        ],
    )


def downgrade() -> None:
    op.execute("ALTER TABLE platform_settings DISABLE TRIGGER platform_settings_immutable")
    op.execute("DELETE FROM platform_settings WHERE version = 4")
    op.execute("ALTER TABLE platform_settings ENABLE TRIGGER platform_settings_immutable")
    op.drop_index("ix_bids_developer_created", table_name="bids")
    op.drop_index("one_standing_bid_per_developer", table_name="bids")
    op.create_index(
        "one_active_bid_per_developer",
        "bids",
        ["project_id", "developer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),  # forbidden-ok: DDL
    )
    op.drop_column("bids", "evaluated_at")
    op.drop_column("bids", "version")
