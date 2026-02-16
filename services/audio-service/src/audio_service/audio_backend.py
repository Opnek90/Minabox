"""Abstract audio backend interface.

Defines the contract that all audio backend implementations must follow.
"""

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel


class PlaybackState(str, Enum):
    """Playback state enumeration."""

    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"


class AudioStatus(BaseModel):
    """Current audio playback status."""

    state: PlaybackState
    track_id: str | None = None
    source_type: str | None = None
    source_uri: str | None = None
    position_ms: int = 0
    duration_ms: int | None = None
    volume: int = 0


class AudioBackend(ABC):
    """Abstract base class for audio backend implementations.

    All audio backends (VLC, GStreamer, etc.) must implement this interface.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the audio backend.

        Raises:
            AudioError: If initialization fails
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the audio backend gracefully."""
        pass

    @abstractmethod
    async def play(
        self,
        source_uri: str,
        start_position_ms: int = 0,
    ) -> None:
        """Start playing audio from source.

        Args:
            source_uri: Path or URL to audio source
            start_position_ms: Start position in milliseconds

        Raises:
            PlaybackError: If playback fails
            FileNotFoundError: If source file doesn't exist
            StreamUnreachableError: If stream is unreachable
        """
        pass

    @abstractmethod
    async def pause(self) -> None:
        """Pause current playback.

        Raises:
            PlaybackError: If pause fails
        """
        pass

    @abstractmethod
    async def resume(self) -> None:
        """Resume paused playback.

        Raises:
            PlaybackError: If resume fails
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop current playback.

        Raises:
            PlaybackError: If stop fails
        """
        pass

    @abstractmethod
    async def set_volume(self, volume: int) -> None:
        """Set playback volume.

        Args:
            volume: Volume level (0-100)

        Raises:
            PlaybackError: If volume change fails
        """
        pass

    @abstractmethod
    async def get_volume(self) -> int:
        """Get current volume level.

        Returns:
            Current volume (0-100)
        """
        pass

    @abstractmethod
    async def get_position(self) -> int:
        """Get current playback position.

        Returns:
            Current position in milliseconds
        """
        pass

    @abstractmethod
    async def get_duration(self) -> int | None:
        """Get total duration of current media.

        Returns:
            Duration in milliseconds, or None if unknown
        """
        pass

    @abstractmethod
    async def get_state(self) -> PlaybackState:
        """Get current playback state.

        Returns:
            Current playback state
        """
        pass

    @abstractmethod
    async def get_status(self) -> AudioStatus:
        """Get complete audio status.

        Returns:
            AudioStatus object with all current information
        """
        pass

    @abstractmethod
    def is_playing(self) -> bool:
        """Check if audio is currently playing.

        Returns:
            True if playing, False otherwise
        """
        pass
