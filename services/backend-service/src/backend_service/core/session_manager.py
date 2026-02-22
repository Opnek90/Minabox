"""Playback session manager for tracking current playback state."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import structlog

from backend_service.models.database import Track

logger = structlog.get_logger(__name__)

RepeatMode = Literal["none", "all"]


@dataclass(frozen=True)
class SessionTrack:
    """Snapshot of track data for playback session (avoids detached ORM instances)."""

    id: int
    source_type: str
    source_uri: str
    title: str = ""
    artist: str = ""
    album: str = ""


@dataclass
class PlaybackSession:
    """Represents an active playback session."""

    playlist_id: int | None = None
    tracks: list[SessionTrack] = field(default_factory=list)
    current_track_index: int = 0
    shuffle: bool = False
    repeat_mode: RepeatMode = "none"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def current_track(self) -> SessionTrack | None:
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

    def next_track(self) -> SessionTrack | None:
        """Move to next track.

        Returns:
            Next track or None if at end
        """
        if self.has_next:
            self.current_track_index += 1
            self.updated_at = datetime.now(UTC)
            return self.current_track
        return None

    def prev_track(self) -> SessionTrack | None:
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
        shuffle: bool = False,
    ) -> PlaybackSession:
        """Create a new playback session.

        Copies track data into SessionTrack snapshots so the session does not
        hold ORM objects across request boundaries (avoids DetachedInstanceError).

        Args:
            tracks: List of tracks to play (must be loaded in active DB session)
            playlist_id: Optional playlist ID if session is from a playlist
            shuffle: If True, shuffle track order (used for playlist playback)

        Returns:
            Created session
        """
        snapshots = [
            SessionTrack(
                id=t.id,
                source_type=t.source_type,
                source_uri=t.source_uri,
                title=t.title or "",
                artist=t.artist or "",
                album=t.album or "",
            )
            for t in tracks
        ]
        if shuffle and len(snapshots) > 1:
            random.shuffle(snapshots)
        self._session = PlaybackSession(
            playlist_id=playlist_id,
            tracks=snapshots,
            current_track_index=0,
            shuffle=shuffle,
            repeat_mode="none",
        )
        logger.info(
            "session_created",
            playlist_id=playlist_id,
            track_count=len(snapshots),
            first_track_id=snapshots[0].id if snapshots else None,
            shuffle=shuffle,
        )
        return self._session

    def set_repeat_mode(self, mode: RepeatMode) -> None:
        """Set repeat mode for current session."""
        if self._session:
            self._session.repeat_mode = mode

    def set_shuffle(self, value: bool) -> None:
        """Set shuffle on/off for current session."""
        if self._session:
            self._session.shuffle = value
            self._session.updated_at = datetime.now(UTC)

    def toggle_shuffle(self) -> bool:
        """Toggle shuffle for current session. Returns new shuffle state."""
        if not self._session:
            return False
        self._session.shuffle = not self._session.shuffle
        self._session.updated_at = datetime.now(UTC)
        return self._session.shuffle

    def get_repeat_mode(self) -> RepeatMode:
        """Get current repeat mode (from session or default none)."""
        if self._session:
            return self._session.repeat_mode
        return "none"

    def get_queue(self) -> list[dict] | None:
        """Get current queue: list of {track_id, title, artist, index, is_current} for API."""
        if not self._session or not self._session.tracks:
            return None
        return [
            {
                "track_id": t.id,
                "title": t.title,
                "artist": t.artist,
                "album": t.album,
                "index": i,
                "is_current": i == self._session.current_track_index,
            }
            for i, t in enumerate(self._session.tracks)
        ]

    def clear_session(self) -> None:
        """Clear current session."""
        if self._session:
            logger.info(
                "session_cleared",
                playlist_id=self._session.playlist_id,
                track_count=len(self._session.tracks),
            )
        self._session = None

    def next_track(self) -> SessionTrack | None:
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

    def prev_track(self) -> SessionTrack | None:
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

    def get_current_track(self) -> SessionTrack | None:
        """Get current track from session (snapshot, not ORM)."""
        if not self._session:
            return None
        return self._session.current_track


# Global session manager instance
session_manager = SessionManager()
