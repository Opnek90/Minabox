"""Shared utilities for MQTT handlers."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend_service.core.session_manager import session_manager
from backend_service.models.database import PlaybackEvent


def close_open_playback_event(
    db_session: Session,
    status_data: dict[str, Any] | None = None,
    accumulated_ms: int | None = None,
) -> None:
    """Close the latest open playback event and persist listened_ms.

    Priority for listened_ms (fix #58):
    1. accumulated_ms  — in-memory wall-clock delta tracked by AudioHandler (works for streams too)
    2. position_ms from status_data — fallback for regular tracks (VLC reports real position)
    3. NULL           — if neither is available (stats will count 0 for this event)
    """
    open_event = (
        db_session.query(PlaybackEvent)
        .filter(PlaybackEvent.ended_at.is_(None))
        .order_by(PlaybackEvent.started_at.desc())
        .first()
    )
    if not open_event:
        return

    open_event.ended_at = datetime.now(UTC)

    if accumulated_ms is not None and accumulated_ms >= 0:
        # Prefer in-memory accumulator (accurate for streams and regular tracks)
        open_event.listened_ms = accumulated_ms
    elif status_data:
        pos = status_data.get("position_ms")
        dur = status_data.get("duration_ms")
        if pos is not None and isinstance(pos, (int, float)) and int(pos) > 0:
            # Only use position_ms if it's > 0 (streams always report 0 — skip them)
            ms = int(pos)
            if dur is not None and isinstance(dur, (int, float)) and int(dur) > 0:
                ms = min(ms, int(dur))
            open_event.listened_ms = ms
        # If position_ms == 0 (stream), leave listened_ms as NULL — will be 0 in stats

    db_session.commit()


def create_playback_event_for_current_track(db_session: Session) -> bool:
    """Create a new PlaybackEvent for session_manager's current track. Returns True if created."""
    sess = session_manager.session
    if not sess or not sess.current_track:
        return False
    track = sess.current_track
    content_type = "playlist" if sess.playlist_id is not None else "track"
    event = PlaybackEvent(
        started_at=datetime.now(UTC),
        content_type=content_type,
        track_id=track.id,
        playlist_id=sess.playlist_id,
        tag_id=None,
    )
    db_session.add(event)
    db_session.commit()
    return True
