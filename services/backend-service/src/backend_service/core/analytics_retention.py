"""Background task: prune old analytics rows (issue #170).

``playback_events`` and ``tag_scan_events`` are data about a child. Keeping
them forever is an implicit decision nobody made; this loop enforces an
explicit one. The retention window is configurable in the WebUI
(``analytics_retention_weeks`` in ``general_settings.json``); ``0`` disables
pruning and keeps everything.

The delete pattern mirrors the retention delete in
:mod:`backend_service.core.temperature_logger`; the loop shape mirrors
:func:`backend_service.core.podcast_fetcher.run_podcast_fetch_loop`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend_service.core.general_settings import read_general_settings

if TYPE_CHECKING:
    from backend_service.core.db_manager import DatabaseManager

logger = structlog.get_logger(__name__)

CLEANUP_INTERVAL_SECONDS = 24 * 3600
INITIAL_DELAY_SECONDS = 120

# Default: one year. Existing installs apply this on the first run after the
# update, so events older than a year (including their contribution to the
# all-time total) are removed.
DEFAULT_RETENTION_WEEKS = 52
MAX_RETENTION_WEEKS = 520


def read_retention_weeks() -> int:
    """Weeks of analytics history to keep. ``0`` means keep forever."""
    try:
        raw = read_general_settings().get(
            "analytics_retention_weeks", DEFAULT_RETENTION_WEEKS
        )
        return max(0, min(MAX_RETENTION_WEEKS, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_WEEKS


def purge_once(session: Session) -> int:
    """Delete analytics rows older than the retention window. Returns rows deleted."""
    weeks = read_retention_weeks()
    if weeks <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(weeks=weeks)
    deleted = 0
    for table, column in (
        ("playback_events", "started_at"),
        ("tag_scan_events", "scanned_at"),
    ):
        result = session.execute(
            text(f"DELETE FROM {table} WHERE {column} < :cutoff"),  # noqa: S608 - fixed identifiers
            {"cutoff": cutoff},
        )
        deleted += result.rowcount or 0
    session.commit()
    if deleted:
        logger.info("analytics_retention_purged", rows=deleted, keep_weeks=weeks)
    return deleted


async def run_analytics_retention_loop(db_manager: DatabaseManager | None) -> None:
    """Prune old analytics rows shortly after start, then once every 24 h."""
    if not db_manager:
        return

    await asyncio.sleep(INITIAL_DELAY_SECONDS)

    while True:
        session = db_manager.get_session()
        try:
            purge_once(session)
        except asyncio.CancelledError:
            session.close()
            break
        except Exception as e:
            logger.warning("analytics_retention_purge_failed", error=str(e))
            session.rollback()
        session.close()

        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break

    logger.info("analytics_retention_loop_stopped")


__all__ = [
    "DEFAULT_RETENTION_WEEKS",
    "MAX_RETENTION_WEEKS",
    "purge_once",
    "read_retention_weeks",
    "run_analytics_retention_loop",
]
