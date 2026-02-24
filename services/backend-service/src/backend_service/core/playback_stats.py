"""Helpers for playback statistics (e.g. daily listening time)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend_service.models.database import PlaybackEvent

# Max minutes per event to count (avoids runaway/buggy events blowing up the total)
MAX_MINUTES_PER_EVENT = 480.0  # 8 hours


def get_today_listened_minutes(db: Session) -> float:
    """Sum listening minutes from completed playback events today (UTC date).
    Each event is capped at MAX_MINUTES_PER_EVENT to avoid one buggy event dominating."""
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
            minutes = duration_sec / 60.0
            if minutes > 0:
                total_minutes += min(minutes, MAX_MINUTES_PER_EVENT)
    return total_minutes


def get_total_listened_minutes(db: Session) -> float:
    """Sum listening minutes from all completed playback events (with same per-event cap)."""
    events = (
        db.query(PlaybackEvent)
        .filter(PlaybackEvent.ended_at.isnot(None))
        .all()
    )
    total_minutes = 0.0
    for e in events:
        if e.ended_at is not None:
            duration_sec = (e.ended_at - e.started_at).total_seconds()
            minutes = duration_sec / 60.0
            if minutes > 0:
                total_minutes += min(minutes, MAX_MINUTES_PER_EVENT)
    return total_minutes
