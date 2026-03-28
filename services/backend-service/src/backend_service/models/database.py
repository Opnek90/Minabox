"""SQLAlchemy database models for Backend Service."""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class PlaybackEvent(Base):
    """One playback session (track/stream/playlist) for analytics."""

    __tablename__ = "playback_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    track_id = Column(Integer, ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True)
    stream_id = Column(Integer, ForeignKey("streams.id", ondelete="SET NULL"), nullable=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id", ondelete="SET NULL"), nullable=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="SET NULL"), nullable=True)
    podcast_id = Column(Integer, ForeignKey("podcasts.id", ondelete="SET NULL"), nullable=True)
    content_type = Column(String(16), nullable=False)  # 'playlist', 'track', 'stream', 'podcast'
    listened_ms = Column(Integer, nullable=True)


class TagScanEvent(Base):
    """One RFID scan event — recorded for every tag scan attempt (issue #72)."""

    __tablename__ = "tag_scan_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag_uid = Column(String(32), nullable=False, index=True)
    tag_name = Column(String(255), nullable=True)
    media_title = Column(String(512), nullable=True)
    media_type = Column(String(16), nullable=True)
    action = Column(String(16), nullable=False)
    scanned_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<TagScanEvent(id={self.id}, tag_uid={self.tag_uid!r}, "
            f"action={self.action!r}, scanned_at={self.scanned_at})>"
        )


class Tag(Base):
    """RFID tag to content mapping."""

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag_id = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    # content_type and content_id are nullable to support unassigned tags
    content_type = Column(String(16), nullable=True)
    content_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(UTC), nullable=True)
    last_scanned_at = Column(DateTime, nullable=True)
    disabled = Column(Boolean, nullable=False, default=False, server_default="0")

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, tag_id={self.tag_id}, content_type={self.content_type}, content_id={self.content_id}, disabled={self.disabled})>"


class Playlist(Base):
    """Audio playlist."""

    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    cover_art_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(UTC), nullable=True)

    tracks = relationship(
        "PlaylistTrack", back_populates="playlist", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Playlist(id={self.id}, name={self.name})>"


class Stream(Base):
    """Audio stream (e.g. web radio). Not part of playlists."""

    __tablename__ = "streams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    artist = Column(String(255), nullable=True)
    source_uri = Column(String(1024), nullable=False)
    cover_art_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    last_played_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<Stream(id={self.id}, title={self.title})>"


class TrackFolder(Base):
    """Logical folder to group tracks in the media library."""

    __tablename__ = "track_folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    parent_id = Column(
        Integer, ForeignKey("track_folders.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(UTC), nullable=True)

    children = relationship(
        "TrackFolder",
        backref=__import__("sqlalchemy.orm", fromlist=["backref"]).backref("parent", remote_side="TrackFolder.id"),
        foreign_keys="TrackFolder.parent_id",
    )

    def __repr__(self) -> str:
        return f"<TrackFolder(id={self.id}, name={self.name}, parent_id={self.parent_id})>"


class Track(Base):
    """Audio track (file or remote). Used in playlists."""

    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    artist = Column(String(255), nullable=True)
    album = Column(String(255), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    source_type = Column(String(16), nullable=False)
    source_uri = Column(String(1024), nullable=False)
    cover_art_url = Column(String(512), nullable=True)
    folder_id = Column(
        Integer, ForeignKey("track_folders.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    last_played_at = Column(DateTime, nullable=True)

    folder = relationship("TrackFolder", foreign_keys=[folder_id])

    def __repr__(self) -> str:
        return (
            f"<Track(id={self.id}, title={self.title}, source_type={self.source_type}, folder_id={self.folder_id})>"
        )


class PlaylistTrack(Base):
    """Many-to-many relationship between playlists and tracks with ordering."""

    __tablename__ = "playlist_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    playlist_id = Column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    track_id = Column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    position = Column(Integer, nullable=False)

    playlist = relationship("Playlist", back_populates="tracks")
    track = relationship("Track")

    __table_args__ = (
        UniqueConstraint("playlist_id", "position", name="unique_playlist_position"),
    )

    def __repr__(self) -> str:
        return f"<PlaylistTrack(playlist_id={self.playlist_id}, track_id={self.track_id}, position={self.position})>"


class Podcast(Base):
    """Podcast feed (RSS)."""

    __tablename__ = "podcasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    rss_url = Column(String(1024), nullable=False)
    description = Column(String(2000), nullable=True)
    cover_art_url = Column(String(512), nullable=True)
    last_fetched_at = Column(DateTime, nullable=True)
    last_played_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    def __repr__(self) -> str:
        return f"<Podcast(id={self.id}, title={self.title})>"


class PodcastEpisode(Base):
    """Single episode of a podcast."""

    __tablename__ = "podcast_episodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    podcast_id = Column(
        Integer, ForeignKey("podcasts.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(512), nullable=False)
    source_uri = Column(String(1024), nullable=False)
    guid = Column(String(512), nullable=True)
    published_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        UniqueConstraint("podcast_id", "source_uri", name="uq_podcast_episode_uri"),
    )

    def __repr__(self) -> str:
        return f"<PodcastEpisode(id={self.id}, podcast_id={self.podcast_id}, title={self.title})>"


class TemperatureReading(Base):
    """One system temperature sample (e.g. Raspberry Pi CPU) for analytics."""

    __tablename__ = "temperature_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recorded_at = Column(DateTime, nullable=False)
    temperature_celsius = Column(Float, nullable=False)

    def __repr__(self) -> str:
        return f"<TemperatureReading(id={self.id}, recorded_at={self.recorded_at}, temperature_celsius={self.temperature_celsius})>"


class TrackResumePosition(Base):
    """Persisted playback resume position per content URI."""

    __tablename__ = "track_resume_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_uri = Column(String(1024), nullable=False, unique=True, index=True)
    position_ms = Column(Integer, nullable=False, default=0)
    content_type = Column(String(16), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<TrackResumePosition("
            f"source_uri={self.source_uri!r}, "
            f"position_ms={self.position_ms}, "
            f"content_type={self.content_type!r})>"
        )
