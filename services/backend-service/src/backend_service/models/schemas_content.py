from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .schemas_enums import ContentType, SourceType


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


class StreamBase(BaseModel):
    """Base schema for streams."""

    title: str = Field(..., min_length=1, max_length=255, description="Stream title")
    artist: str | None = Field(
        None, max_length=255, description="Artist or station name"
    )
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
    cover_art_url: str | None = None
    created_at: datetime
    last_played_at: datetime | None = None

    class Config:
        from_attributes = True


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
    last_played_at: datetime | None = None
    created_at: datetime
    latest_episode_title: str | None = None
    latest_episode_published_at: datetime | None = None

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


__all__ = [
    "TagBase",
    "TagCreate",
    "TagUpdate",
    "TagResponse",
    "PlaylistBase",
    "PlaylistCreate",
    "PlaylistUpdate",
    "PlaylistResponse",
    "PlaylistDetailResponse",
    "StreamBase",
    "StreamCreate",
    "StreamUpdate",
    "StreamResponse",
    "PodcastBase",
    "PodcastCreate",
    "PodcastUpdate",
    "PodcastResponse",
    "PodcastEpisodeResponse",
    "TrackBase",
    "TrackCreate",
    "TrackUpdate",
    "TrackResponse",
]

