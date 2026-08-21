"""Add stream_folders/podcast_folders tables and folder_id to streams/podcasts.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _create_folder_table(inspector: sa.Inspector, table_name: str) -> None:
    """Create <table_name> unless it already exists.

    `Base.metadata.create_all()` runs on every backend start *before* this
    migration and already creates any table that is missing from the current
    models - including brand new ones like this. On a box where that already
    happened, `op.create_table` here would fail with "table already exists"
    and abort the whole migration function, silently skipping the column
    additions further down. Checking first keeps this step a no-op instead.
    """
    if table_name in inspector.get_table_names():
        return
    op.create_table(
        table_name,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            [f"{table_name}.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def _add_folder_id_column(
    inspector: sa.Inspector, table_name: str, folder_table: str, fk_name: str
) -> None:
    """Add `folder_id` + its FK to <table_name> unless the column already exists."""
    existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
    if "folder_id" in existing_columns:
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(sa.Column("folder_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            fk_name, folder_table, ["folder_id"], ["id"], ondelete="SET NULL"
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _create_folder_table(inspector, "stream_folders")
    _add_folder_id_column(inspector, "streams", "stream_folders", "fk_streams_folder_id")

    _create_folder_table(inspector, "podcast_folders")
    _add_folder_id_column(inspector, "podcasts", "podcast_folders", "fk_podcasts_folder_id")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "folder_id" in {c["name"] for c in inspector.get_columns("podcasts")}:
        with op.batch_alter_table("podcasts") as batch_op:
            batch_op.drop_constraint("fk_podcasts_folder_id", type_="foreignkey")
            batch_op.drop_column("folder_id")
    if "podcast_folders" in inspector.get_table_names():
        op.drop_table("podcast_folders")

    if "folder_id" in {c["name"] for c in inspector.get_columns("streams")}:
        with op.batch_alter_table("streams") as batch_op:
            batch_op.drop_constraint("fk_streams_folder_id", type_="foreignkey")
            batch_op.drop_column("folder_id")
    if "stream_folders" in inspector.get_table_names():
        op.drop_table("stream_folders")
