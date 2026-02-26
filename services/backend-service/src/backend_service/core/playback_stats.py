"""Helpers for playback statistics (e.g. daily listening time)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend_service.models.database import PlaybackEvent

# Max minutes per event to count (avoids runaway/buggy events blowing up the total)
MAX_MINUTES_PER_EVENT = 480.0  # 8 hours


def minutes_for_event(e: PlaybackEvent) -> float:
    """Listening minutes for one completed event: use listened_ms if set, else wall-clock. Capped at MAX_MINUTES_PER_EVENT."""
    if e.ended_at is None:
        return 0.0
    if getattr(e, "listened_ms", None) is not None and e.listened_ms is not None:
        minutes = e.listened_ms / 60_000.0
    else:
        duration_sec = (e.ended_at - e.started_at).total_seconds()
        minutes = duration_sec / 60.0
    return min(minutes, MAX_MINUTES_PER_EVENT) if minutes > 0 else 0.0


def get_today_listened_minutes(db: Session) -> float:
    """Sum listening minutes from completed playback events that ended today (local date).
    Uses host/system timezone (e.g. TZ env) for 'today'. Each event capped at MAX_MINUTES_PER_EVENT."""
    now_utc = datetime.now(UTC)
    # Local "today" boundaries (uses process timezone, typically from host TZ)
    try:
        local_now = now_utc.astimezone()
    except Exception:
        local_now = now_utc
    start_of_day_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day_local = start_of_day_local + timedelta(days=1) - timedelta(microseconds=1)
    start_utc = start_of_day_local.astimezone(UTC)
    end_utc = end_of_day_local.astimezone(UTC)
    events = (
        db.query(PlaybackEvent)
        .filter(
            PlaybackEvent.ended_at.isnot(None),
            PlaybackEvent.ended_at >= start_utc,
            PlaybackEvent.ended_at <= end_utc,
        )
        .all()
    )
    return sum(minutes_for_event(e) for e in events)


def get_total_listened_minutes(db: Session) -> float:
    """Sum listening minutes from all completed playback events (with same per-event cap)."""
    events = (
        db.query(PlaybackEvent)
        .filter(PlaybackEvent.ended_at.isnot(None))
        .all()
    )
    return sum(minutes_for_event(e) for e in events)
