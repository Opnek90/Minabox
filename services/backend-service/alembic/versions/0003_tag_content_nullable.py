"""Make tags.content_id and tags.content_type nullable (unassigned tags)

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-15

Issue #64: Tags can now exist without an assigned content item.
After deleting a medium with "Medium + Tag-Zuweisung l\u00f6schen", the tag's
content_id and content_type are set to NULL instead of keeping a stale
reference. The frontend filter "Ohne Inhalt" uses this to list unassigned tags.

SQLite does not support ALTER COLUMN directly, so we use batch_alter_table
(renders as a full table rebuild under the hood).
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tags") as batch_op:
        batch_op.alter_column(
            "content_type",
            existing_type=sa.String(length=16),
            nullable=True,
        )
        batch_op.alter_column(
            "content_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    # Back-fill any NULLs before re-applying NOT NULL constraint
    op.execute("UPDATE tags SET content_type = 'track' WHERE content_type IS NULL")
    op.execute("UPDATE tags SET content_id = 0 WHERE content_id IS NULL")

    with op.batch_alter_table("tags") as batch_op:
        batch_op.alter_column(
            "content_type",
            existing_type=sa.String(length=16),
            nullable=False,
        )
        batch_op.alter_column(
            "content_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
