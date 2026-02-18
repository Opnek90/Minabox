"""State manager for audio playback state persistence.

Manages playback state and supports resume functionality.
"""

import json
from pathlib import Path

import structlog
from pydantic import BaseModel, ValidationError

from .audio_backend import PlaybackState
from .exceptions import StateError

logger = structlog.get_logger(__name__)


class AudioState(BaseModel):
    """Persisted audio playback state."""

    last_track_id: str | None = None
    last_source_type: str | None = None
    last_source_uri: str | None = None
    last_position_ms: int = 0
    last_state: str = PlaybackState.STOPPED.value
    last_volume: int = 40


class StateManager:
    """Manages audio playback state with optional persistence.

    Tracks current playback state and can persist/restore state
    for resume functionality after service restarts.
    """

    def __init__(self, state_file_path: Path) -> None:
        """Initialize state manager.

        Args:
            state_file_path: Path to state persistence file
        """
        self._state_file_path = state_file_path
        self._state = AudioState()

    def load(self) -> AudioState:
        """Load state from file.

        Returns:
            Loaded AudioState, or default state if file doesn't exist

        Raises:
            StateError: If state loading fails
        """
        if not self._state_file_path.exists():
            logger.info(
                "state_file_not_found_using_default",
                path=str(self._state_file_path),
            )
            return AudioState()

        try:
            with open(self._state_file_path, encoding="utf-8") as f:
                data = json.load(f)

            self._state = AudioState(**data)

            logger.info(
                "state_loaded",
                path=str(self._state_file_path),
                last_track_id=self._state.last_track_id,
            )

            return self._state

        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(
                "state_load_failed_using_default",
                path=str(self._state_file_path),
                error=str(e),
            )
            return AudioState()
        except Exception as e:
            logger.error("state_load_error", error=str(e))
            raise StateError(f"Failed to load state: {e}") from e

    def save(self, state: AudioState) -> None:
        """Save state to file.

        Args:
            state: AudioState to persist

        Raises:
            StateError: If state saving fails
        """
        try:
            # Ensure directory exists
            self._state_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write state
            with open(self._state_file_path, "w", encoding="utf-8") as f:
                json.dump(state.model_dump(), f, indent=2)

            self._state = state

            logger.debug(
                "state_saved",
                path=str(self._state_file_path),
            )

        except Exception as e:
            logger.error("state_save_error", error=str(e))
            raise StateError(f"Failed to save state: {e}") from e

    def update_playback(
        self,
        track_id: str | None = None,
        source_type: str | None = None,
        source_uri: str | None = None,
        position_ms: int | None = None,
        state: PlaybackState | None = None,
        volume: int | None = None,
    ) -> None:
        """Update playback state and persist.

        Args:
            track_id: Current track ID
            source_type: Source type
            source_uri: Source URI
            position_ms: Current position
            state: Playback state
            volume: Current volume
        """
        if track_id is not None:
            self._state.last_track_id = track_id
        if source_type is not None:
            self._state.last_source_type = source_type
        if source_uri is not None:
            self._state.last_source_uri = source_uri
        if position_ms is not None:
            self._state.last_position_ms = position_ms
        if state is not None:
            self._state.last_state = state.value
        if volume is not None:
            self._state.last_volume = volume

        # Auto-save on update
        self.save(self._state)

    def get_state(self) -> AudioState:
        """Get current state.

        Returns:
            Current AudioState
        """
        return self._state

    def clear(self) -> None:
        """Clear state (reset to default)."""
        self._state = AudioState()
        self.save(self._state)
        logger.info("state_cleared")

    def can_resume(self) -> bool:
        """Check if resume is possible (we have a last source to resume).

        Returns:
            True if we have a last source URI (stream or file) to resume.
        """
        return self._state.last_source_uri is not None
