"""CRUD helpers for per-track playback resume positions.

Positions are stored in the ``track_resume_positions`` SQLite table
(see TrackResumePosition model) and keyed by ``source_uri`` — the only
identifier shared between audio-service and backend-service.

Save semantics
--------------
* Do NOT save if position < MIN_SAVE_POSITION_MS  (user barely started)
* Do NOT save if remaining time < MIN_REMAINING_MS (track almost done)
  → in that case delete any existing entry so next play starts from 0
* Otherwise upsert: update if row exists, insert if not
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.orm import Session

from backend_service.models.database import TrackResumePosition

logger = structlog.get_logger(__name__)

# --- tuneable thresholds -----------------------------------------------
# Position below this value is considered "at the start" — not worth saving.
MIN_SAVE_POSITION_MS: int = 5_000   # 5 s

# If less than this amount of content remains the track is considered
# "finished" — clear the stored position so next play starts from 0.
MIN_REMAINING_MS: int = 10_000      # 10 s
# -----------------------------------------------------------------------


def save_resume_position(
    session: Session,
    source_uri: str,
    position_ms: int,
    content_type: str,
    duration_ms: int | None = None,
) -> None:
    """Persist (or update) the resume position for *source_uri*.

    Parameters
    ----------
    session:
        Active SQLAlchemy session.  The caller is responsible for
        closing it.
    source_uri:
        Unique audio content identifier (shared with audio-service).
    position_ms:
        Current playback position in milliseconds at the time of stop/pause.
    content_type:
        ``'track'`` or ``'podcast'`` — stored for informational purposes
        and future filtering.
    duration_ms:
        Total track duration in milliseconds.  When provided the
        "near-end" heuristic is applied.
    """
    if not source_uri:
        return

    # Guard: too early in the track — not worth resuming
    if position_ms < MIN_SAVE_POSITION_MS:
        logger.debug(
            "resume_position_skip_too_early",
            source_uri=source_uri,
            position_ms=position_ms,
        )
        return

    # Guard: track almost finished — clear so next play starts from beginning
    if duration_ms is not None and (duration_ms - position_ms) < MIN_REMAINING_MS:
        clear_resume_position(session, source_uri)
        logger.debug(
            "resume_position_cleared_near_end",
            source_uri=source_uri,
            position_ms=position_ms,
            duration_ms=duration_ms,
        )
        return

    existing = (
        session.query(TrackResumePosition)
        .filter_by(source_uri=source_uri)
        .first()
    )
    if existing:
        existing.position_ms = position_ms
        existing.updated_at = datetime.now(UTC)
    else:
        session.add(
            TrackResumePosition(
                source_uri=source_uri,
                position_ms=position_ms,
                content_type=content_type,
                updated_at=datetime.now(UTC),
            )
        )
    session.commit()
    logger.debug(
        "resume_position_saved",
        source_uri=source_uri,
        position_ms=position_ms,
        content_type=content_type,
    )


def get_resume_position(session: Session, source_uri: str) -> int:
    """Return the stored resume position for *source_uri*, or ``0``.

    Parameters
    ----------
    session:
        Active SQLAlchemy session.
    source_uri:
        Audio content identifier to look up.

    Returns
    -------
    int
        Saved position in milliseconds, or ``0`` if no entry exists.
    """
    if not source_uri:
        return 0
    entry = (
        session.query(TrackResumePosition)
        .filter_by(source_uri=source_uri)
        .first()
    )
    return entry.position_ms if entry else 0


def clear_resume_position(session: Session, source_uri: str) -> None:
    """Delete the stored resume position for *source_uri* if it exists.

    Called when a track has been played to completion so the next
    playback starts from the beginning.

    Parameters
    ----------
    session:
        Active SQLAlchemy session.
    source_uri:
        Audio content identifier whose entry should be removed.
    """
    if not source_uri:
        return
    deleted = (
        session.query(TrackResumePosition)
        .filter_by(source_uri=source_uri)
        .delete()
    )
    if deleted:
        session.commit()
        logger.debug("resume_position_cleared", source_uri=source_uri)
