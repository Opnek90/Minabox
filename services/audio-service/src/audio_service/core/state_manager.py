"""State manager for audio playback state persistence."""

import json
import os
import tempfile
from pathlib import Path

import structlog
from pydantic import BaseModel, ValidationError

from ..exceptions import StateError
from ..infrastructure.audio_backend import PlaybackState

logger = structlog.get_logger(__name__)


class AudioState(BaseModel):
    """Persisted audio playback state."""
    last_track_id: str | None = None
    last_source_type: str | None = None
    last_source_uri: str | None = None
    last_position_ms: int = 0
    last_state: str = PlaybackState.STOPPED.value
    # 0 means "nothing remembered yet", which is what the service checks for
    # before falling back to default_volume. A non-zero default here would be
    # mistaken for a remembered volume on a box that has never played anything,
    # and default_volume would never apply.
    last_volume: int = 0


class StateManager:
    """Manages audio playback state with optional persistence."""

    def __init__(self, state_file_path: Path) -> None:
        self._state_file_path = state_file_path
        self._state = AudioState()

    def load(self) -> AudioState:
        if not self._state_file_path.exists():
            logger.debug(
                "state_file_not_found_using_default",
                path=str(self._state_file_path),
            )
            return AudioState()
        try:
            with open(self._state_file_path, encoding="utf-8") as f:
                data = json.load(f)
            self._state = AudioState(**data)
            logger.debug(
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
        """Persist the state atomically.

        The box is meant to survive having its plug pulled at any moment. A
        plain open("w") truncates the file first, so losing power mid-write
        left a half-written JSON behind. Writing to a temp file in the same
        directory and renaming it means readers only ever see a complete file.
        """
        try:
            self._state_file_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self._state_file_path.parent),
                prefix=f".{self._state_file_path.name}.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(state.model_dump(), f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_name, self._state_file_path)
            except Exception:
                Path(tmp_name).unlink(missing_ok=True)
                raise
            self._state = state
            logger.debug("state_saved", path=str(self._state_file_path))
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
        self.save(self._state)

    def get_state(self) -> AudioState:
        return self._state

    def clear(self) -> None:
        self._state = AudioState()
        self.save(self._state)
        logger.debug("state_cleared")

    def can_resume(self) -> bool:
        return self._state.last_source_uri is not None
