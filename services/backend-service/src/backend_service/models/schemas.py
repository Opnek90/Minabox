"""Pydantic schemas for REST API and internal data validation."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ============================================================================
# Enums
# ============================================================================


class ContentType(str, Enum):
    """Content type for RFID tag mapping."""

    PLAYLIST = "playlist"
    TRACK = "track"
    STREAM = "stream"
    PODCAST = "podcast"


class SourceType(str, Enum):
    """Source type for audio tracks (file = local, remote = NAS/DLNA/CIFS/NFS/SMB)."""

    FILE = "file"
    REMOTE = "remote"


class AudioState(str, Enum):
    """Audio playback state."""

    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"


class ServiceState(str, Enum):
    """Service health state."""

    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class RFIDMode(str, Enum):
    """RFID reader mode."""

    NORMAL = "normal"
    LEARNING = "learning"


# ============================================================================
# Tags
# ============================================================================


class TagBase(BaseModel):
    """Base schema for RFID tags."""

    tag_id: str = Field(..., description="RFID tag UID (e.g., 04A224BC19)")
    name: str | None = Field(None, description="Human-readable name")
    content_type: ContentType = Field(
        ..., description="Type of content (playlist/track/stream)"
    )
    content_id: int = Field(..., description="ID of playlist, track or stream", gt=0)


class TagCreate(TagBase):
    """Schema for creating a new tag mapping."""

    pass


class TagUpdate(BaseModel):
    """Schema for updating an existing tag."""

    name: str | None = None
    content_type: ContentType | None = None
    content_id: int | None = Field(None, gt=0)


class TagResponse(TagBase):
    """Schema for tag API response."""

    id: int
    created_at: datetime
    updated_at: datetime | None = None
    last_scanned_at: datetime | None = None

    class Config:
        from_attributes = True


# ============================================================================
# Playlists
# ============================================================================


class PlaylistBase(BaseModel):
    """Base schema for playlists."""

    name: str = Field(..., min_length=1, max_length=255, description="Playlist name")
    description: str | None = Field(
        None, max_length=1000, description="Playlist description"
    )


class PlaylistCreate(PlaylistBase):
    """Schema for creating a new playlist."""

    track_ids: list[int] = Field(
        default_factory=list, description="List of track IDs in order"
    )


class PlaylistUpdate(BaseModel):
    """Schema for updating an existing playlist."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    track_ids: list[int] | None = None


class PlaylistResponse(PlaylistBase):
    """Schema for playlist API response (without tracks)."""

    id: int
    cover_art_url: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class PlaylistDetailResponse(PlaylistResponse):
    """Schema for playlist API response with tracks."""

    tracks: list["TrackResponse"] = Field(default_factory=list)


# ============================================================================
# Streams
# ============================================================================


class StreamBase(BaseModel):
    """Base schema for streams."""

    title: str = Field(..., min_length=1, max_length=255, description="Stream title")
    artist: str | None = Field(None, max_length=255, description="Artist or station name")
    source_uri: str = Field(..., description="Stream URL")


class StreamCreate(StreamBase):
    """Schema for creating a new stream."""

    pass


class StreamUpdate(BaseModel):
    """Schema for updating an existing stream."""

    title: str | None = Field(None, min_length=1, max_length=255)
    artist: str | None = None
    source_uri: str | None = None


class StreamResponse(StreamBase):
    """Schema for stream API response."""

    id: int
    created_at: datetime
    last_played_at: datetime | None = None

    class Config:
        from_attributes = True


# ============================================================================
# Podcasts
# ============================================================================


class PodcastBase(BaseModel):
    """Base schema for podcasts."""

    title: str = Field(..., min_length=1, max_length=255, description="Podcast title")
    rss_url: str = Field(..., description="RSS feed URL")
    description: str | None = Field(None, max_length=2000)
    cover_art_url: str | None = Field(None, max_length=512)


class PodcastCreate(PodcastBase):
    """Schema for creating a new podcast."""

    pass


class PodcastUpdate(BaseModel):
    """Schema for updating an existing podcast."""

    title: str | None = Field(None, min_length=1, max_length=255)
    rss_url: str | None = None
    description: str | None = None
    cover_art_url: str | None = None


class PodcastResponse(PodcastBase):
    """Schema for podcast API response."""

    id: int
    last_fetched_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PodcastEpisodeResponse(BaseModel):
    """Schema for a single podcast episode."""

    id: int
    podcast_id: int
    title: str
    source_uri: str
    published_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Tracks
# ============================================================================


class TrackBase(BaseModel):
    """Base schema for audio tracks."""

    title: str = Field(..., min_length=1, max_length=255, description="Track title")
    artist: str | None = Field(None, max_length=255, description="Artist name")
    album: str | None = Field(None, max_length=255, description="Album name")
    source_type: SourceType = Field(
        ..., description="Source type (file = local, remote = NAS/DLNA/CIFS/NFS/SMB)"
    )
    source_uri: str = Field(..., description="File path or remote URI")


class TrackCreate(TrackBase):
    """Schema for creating a new track (without file upload)."""

    duration_ms: int | None = Field(None, ge=0, description="Duration in milliseconds")


class TrackUpdate(BaseModel):
    """Schema for updating an existing track."""

    title: str | None = Field(None, min_length=1, max_length=255)
    artist: str | None = None
    album: str | None = None
    duration_ms: int | None = Field(None, ge=0)


class TrackResponse(TrackBase):
    """Schema for track API response."""

    id: int
    duration_ms: int | None = None
    cover_art_url: str | None = None
    created_at: datetime
    last_played_at: datetime | None = None

    class Config:
        from_attributes = True


# ============================================================================
# Audio Control
# ============================================================================


class AudioPlayCommand(BaseModel):
    """Schema for audio play command."""

    track_id: int | None = Field(None, description="Track ID to play")
    playlist_id: int | None = Field(None, description="Playlist ID to play")
    stream_id: int | None = Field(None, description="Stream ID to play")
    podcast_id: int | None = Field(None, description="Podcast ID (plays latest episode)")
    start_position_ms: int = Field(
        0, ge=0, description="Start position in milliseconds"
    )

    @model_validator(mode="after")
    def validate_single_content(self) -> "AudioPlayCommand":
        """Ensure at most one of track_id, playlist_id, stream_id, podcast_id is provided."""
        provided = sum(
            1
            for v in (self.track_id, self.playlist_id, self.stream_id, self.podcast_id)
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


# ============================================================================
# RFID
# ============================================================================


class RFIDLearningModeCommand(BaseModel):
    """Schema for RFID learning mode command."""

    enabled: bool = Field(..., description="Enable/disable learning mode")


class RFIDScanEvent(BaseModel):
    """Schema for RFID scan event."""

    tag_id: str
    reader_id: str = "pn532_01"
    timestamp: datetime


# ============================================================================
# Service Config
# ============================================================================


class ButtonConfig(BaseModel):
    """Schema for button service configuration."""

    # Simplified - actual schema depends on button service architecture
    debounce_ms: int = Field(
        50, ge=10, le=500, description="Debounce time in milliseconds"
    )
    long_press_ms: int = Field(
        1000, ge=100, le=5000, description="Long press threshold"
    )


class LEDConfig(BaseModel):
    """Schema for LED service configuration."""

    # Simplified - actual schema depends on LED service architecture
    brightness: int = Field(50, ge=0, le=100, description="LED brightness (0-100)")
    animation_speed: int = Field(
        100, ge=10, le=1000, description="Animation speed in ms"
    )


class AudioConfig(BaseModel):
    """Schema for audio service configuration."""

    default_volume: int = Field(50, ge=0, le=100, description="Default volume (0-100)")
    max_volume: int = Field(100, ge=0, le=100, description="Maximum volume (0-100)")


class RFIDConfig(BaseModel):
    """Schema for RFID service configuration."""

    scan_interval_ms: int = Field(
        500, ge=100, le=2000, description="Scan interval in ms"
    )
    retry_attempts: int = Field(
        3, ge=1, le=10, description="Retry attempts on read failure"
    )


# ============================================================================
# System & Health
# ============================================================================


class HealthCheckResponse(BaseModel):
    """Schema for health check response."""

    status: str = Field(..., description="Health status (healthy/unhealthy)")
    service: str = "backend"
    version: str = "0.1.0"
    uptime_seconds: int = Field(..., ge=0)
    mqtt_connected: bool
    database_connected: bool


class ServiceStatus(BaseModel):
    """Schema for individual service status."""

    service: str
    state: ServiceState
    last_seen: datetime | None = None


class SystemStatusResponse(BaseModel):
    """Schema for system status response."""

    backend: ServiceStatus
    audio: ServiceStatus
    rfid: ServiceStatus
    button: ServiceStatus
    led: ServiceStatus
    mqtt_broker: ServiceStatus


# ============================================================================
# WebSocket
# ============================================================================


class WebSocketMessage(BaseModel):
    """Schema for WebSocket messages."""

    type: str = Field(
        ..., description="Message type (e.g., audio_status, rfid_scanned)"
    )
    data: dict[str, Any] = Field(..., description="Message payload")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Error
# ============================================================================


class ErrorDetail(BaseModel):
    """Schema for error details."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Schema for error response."""

    error: ErrorDetail
