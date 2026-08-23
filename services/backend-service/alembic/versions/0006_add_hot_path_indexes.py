"""Index the columns the hot paths filter and sort on.

`playback_events` had no index at all, yet it is touched on every stop (find
the open event, ordered by start time), on every card scan while a daily limit
is set, and on every dashboard request. `temperature_readings` grows by one row
every five minutes and is read as a time range, and the scan history is always
read newest-first.

None of this is noticeable on a fresh box. On an SD card with a year of history
behind it, it is the difference between a query that touches an index and one
that walks the whole table.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_playback_events_started_at", "playback_events", "started_at"),
    ("ix_playback_events_ended_at", "playback_events", "ended_at"),
    ("ix_temperature_readings_recorded_at", "temperature_readings", "recorded_at"),
    ("ix_tag_scan_events_scanned_at", "tag_scan_events", "scanned_at"),
)


def upgrade() -> None:
    # IF NOT EXISTS rather than op.create_index: a database adopted from the
    # old create_all() path may already carry these, because the models declare
    # them too. Revision 0005 guards itself for the same reason.
    for name, table, column in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})")


def downgrade() -> None:
    for name, _, _ in reversed(_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
