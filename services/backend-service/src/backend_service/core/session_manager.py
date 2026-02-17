"""Playback session manager for tracking current playback state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from backend_service.models.database import Track

logger = structlog.get_logger(__name__)


@dataclass
class PlaybackSession:
    """Represents an active playback session."""

    playlist_id: int | None = None
    tracks: list[Track] = field(default_factory=list)
    current_track_index: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def current_track(self) -> Track | None:
        """Get currently playing track.

        Returns:
            Current track or None if no tracks
        """
        if not self.tracks or self.current_track_index >= len(self.tracks):
            return None
        return self.tracks[self.current_track_index]

    @property
    def has_next(self) -> bool:
        """Check if there is a next track.

        Returns:
            True if next track exists
        """
        return self.current_track_index < len(self.tracks) - 1

    @property
    def has_prev(self) -> bool:
        """Check if there is a previous track.

        Returns:
            True if previous track exists
        """
        return self.current_track_index > 0

    def next_track(self) -> Track | None:
        """Move to next track.

        Returns:
            Next track or None if at end
        """
        if self.has_next:
            self.current_track_index += 1
            self.updated_at = datetime.now(UTC)
            return self.current_track
        return None

    def prev_track(self) -> Track | None:
        """Move to previous track.

        Returns:
            Previous track or None if at start
        """
        if self.has_prev:
            self.current_track_index -= 1
            self.updated_at = datetime.now(UTC)
            return self.current_track
        return None

    def reset(self) -> None:
        """Reset session to first track."""
        self.current_track_index = 0
        self.updated_at = datetime.now(UTC)


class SessionManager:
    """Manages playback sessions in memory."""

    def __init__(self) -> None:
        """Initialize session manager."""
        self._session: PlaybackSession | None = None
        logger.info("session_manager_initialized")

    @property
    def session(self) -> PlaybackSession | None:
        """Get current session.

        Returns:
            Current session or None
        """
        return self._session

    def create_session(
        self,
        tracks: list[Track],
        playlist_id: int | None = None,
    ) -> PlaybackSession:
        """Create a new playback session.

        Args:
            tracks: List of tracks to play
            playlist_id: Optional playlist ID if session is from a playlist

        Returns:
            Created session
        """
        self._session = PlaybackSession(
            playlist_id=playlist_id,
            tracks=tracks,
            current_track_index=0,
        )
        logger.info(
            "session_created",
            playlist_id=playlist_id,
            track_count=len(tracks),
            first_track_id=tracks[0].id if tracks else None,
        )
        return self._session

    def clear_session(self) -> None:
        """Clear current session."""
        if self._session:
            logger.info(
                "session_cleared",
                playlist_id=self._session.playlist_id,
                track_count=len(self._session.tracks),
            )
        self._session = None

    def next_track(self) -> Track | None:
        """Move to next track in session.

        Returns:
            Next track or None if no session or at end
        """
        if not self._session:
            logger.warning("session_next_track_no_session")
            return None

        next_track = self._session.next_track()
        if next_track:
            logger.info(
                "session_next_track",
                track_id=next_track.id,
                track_title=next_track.title,
                index=self._session.current_track_index,
            )
        else:
            logger.info("session_next_track_end_of_playlist")
        return next_track

    def prev_track(self) -> Track | None:
        """Move to previous track in session.

        Returns:
            Previous track or None if no session or at start
        """
        if not self._session:
            logger.warning("session_prev_track_no_session")
            return None

        prev_track = self._session.prev_track()
        if prev_track:
            logger.info(
                "session_prev_track",
                track_id=prev_track.id,
                track_title=prev_track.title,
                index=self._session.current_track_index,
            )
        else:
            logger.info("session_prev_track_start_of_playlist")
        return prev_track

    def get_current_track(self) -> Track | None:
        """Get current track from session.

        Returns:
            Current track or None if no session
        """
        if not self._session:
            return None
        return self._session.current_track


# Global session manager instance
session_manager = SessionManager()
