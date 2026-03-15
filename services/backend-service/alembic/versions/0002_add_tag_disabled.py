"""add disabled column to tags table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-15

Issue #63: Tags can now be individually blocked. When disabled=True the
backend will not start playback and instead fires a tag_blocked MQTT event.
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column as nullable first so existing rows are not rejected
    with op.batch_alter_table("tags") as batch_op:
        batch_op.add_column(
            sa.Column("disabled", sa.Boolean(), nullable=True)
        )

    # Back-fill: all existing tags stay enabled (disabled = False / 0)
    op.execute("UPDATE tags SET disabled = 0 WHERE disabled IS NULL")

    # Now tighten the constraint
    with op.batch_alter_table("tags") as batch_op:
        batch_op.alter_column(
            "disabled",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default="0",
        )


def downgrade() -> None:
    with op.batch_alter_table("tags") as batch_op:
        batch_op.drop_column("disabled")
