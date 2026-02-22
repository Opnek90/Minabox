"""Helpers for playback statistics (e.g. daily listening time)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend_service.models.database import PlaybackEvent


def get_today_listened_minutes(db: Session) -> float:
    """Sum listening minutes from completed playback events today (UTC date)."""
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    events = (
        db.query(PlaybackEvent)
        .filter(
            PlaybackEvent.started_at >= start_of_day,
            PlaybackEvent.started_at <= now,
            PlaybackEvent.ended_at.isnot(None),
        )
        .all()
    )
    total_minutes = 0.0
    for e in events:
        if e.ended_at is not None:
            duration_sec = (e.ended_at - e.started_at).total_seconds()
            total_minutes += duration_sec / 60.0
    return total_minutes
