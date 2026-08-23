"""Add track_resume_positions table.

Revision ID: 0001
Revises: (initial)
Create Date: 2026-03-09

Part of Issue #51 — Save Audio State per Track/Podcast for Enhanced
Resume Functionality.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "0001"
down_revision: str | None = "0000"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "track_resume_positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_uri", sa.String(length=1024), nullable=False),
        sa.Column("position_ms", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_uri", name="uq_track_resume_source_uri"),
    )
    op.create_index(
        "ix_track_resume_positions_source_uri",
        "track_resume_positions",
        ["source_uri"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_track_resume_positions_source_uri",
        table_name="track_resume_positions",
    )
    op.drop_table("track_resume_positions")
