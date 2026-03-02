from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .schemas_enums import AudioState, SourceType


class AudioPlayCommand(BaseModel):
    """Schema for audio play command."""

    track_id: int | None = Field(None, description="Track ID to play")
    playlist_id: int | None = Field(None, description="Playlist ID to play")
    stream_id: int | None = Field(None, description="Stream ID to play")
    podcast_id: int | None = Field(None, description="Podcast ID (plays latest episode)")
    start_position_ms: int = Field(
        0,
        ge=0,
        description="Start position in milliseconds",
    )

    @model_validator(mode="after")
    def validate_single_content(self) -> "AudioPlayCommand":
        """Ensure at most one of track_id, playlist_id, stream_id, podcast_id is provided."""
        provided = sum(
            1
            for v in (
                self.track_id,
                self.playlist_id,
                self.stream_id,
                self.podcast_id,
            )
            if v is not None
        )
        if provided > 1:
            raise ValueError(
                "Provide at most one of track_id, playlist_id, stream_id, podcast_id"
            )
        return self


class AudioVolumeCommand(BaseModel):
    """Schema for audio volume command."""

    volume: int = Field(..., ge=0, le=100, description="Volume level (0-100)")


class AudioStatusResponse(BaseModel):
    """Schema for audio status response."""

    state: AudioState
    track_id: int | None = None
    source_type: SourceType | None = None
    source_uri: str | None = None
    position_ms: int | None = None
    duration_ms: int | None = None
    volume: int = Field(..., ge=0, le=100)
    timestamp: datetime


__all__ = [
    "AudioPlayCommand",
    "AudioVolumeCommand",
    "AudioStatusResponse",
]

