"""Per-project minimum standards for the too-few-bids actions (Phase 5 follow-up, spec §9.19).

`projects.min_performance` / `min_competency` override the platform `filter.P0` / `filter.C0` for
one project when its client lowers the standards (NULL = platform default). Scores are on 0–1
like every reputation value (§9.2). The service bounds them to [default − max relaxation,
default] (DECISIONS D54); the check constraints only keep them on the score scale.

Revision ID: 0007_bidding_terms
Revises: 0006_marketplace_bidding
Create Date: 2026-10-22 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_bidding_terms"
down_revision: str | None = "0006_marketplace_bidding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("min_performance", sa.Numeric(3, 2), nullable=True))
    op.add_column("projects", sa.Column("min_competency", sa.Numeric(3, 2), nullable=True))
    op.create_check_constraint(
        op.f("ck_projects_min_performance_range"),
        "projects",
        "min_performance IS NULL OR (min_performance >= 0 AND min_performance <= 1)",
    )
    op.create_check_constraint(
        op.f("ck_projects_min_competency_range"),
        "projects",
        "min_competency IS NULL OR (min_competency >= 0 AND min_competency <= 1)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_projects_min_competency_range"), "projects", type_="check")
    op.drop_constraint(op.f("ck_projects_min_performance_range"), "projects", type_="check")
    op.drop_column("projects", "min_competency")
    op.drop_column("projects", "min_performance")
