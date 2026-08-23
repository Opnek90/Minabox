"""SQLAlchemy database models for Backend Service.

Written in the 2.0 style (``Mapped`` / ``mapped_column``) rather than the legacy
``Column`` form. That is not cosmetic: with the old style every attribute is a
``Column[str]`` as far as a type checker is concerned, so assigning a string to
``track.title`` reads as a type error - which is where the bulk of this
service's type-check noise came from.

Nothing about the generated SQL changes. ``test_schema_migrations.py`` builds
one database from these models and one from the migration chain and compares
columns and indexes, so any drift shows up as a failing test rather than as a
surprise on a fresh install.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    """Timezone-aware creation timestamp. SQLite stores the UTC wall clock."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for all database models."""


class PlaybackEvent(Base):
    """One playback session (track/stream/playlist) for analytics."""

    __tablename__ = "playback_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Indexed: every stop looks for the open event ordered by start time, and
    # the dashboard reads whole day ranges.
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    track_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True
    )
    stream_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("streams.id", ondelete="SET NULL"), nullable=True
    )
    playlist_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="SET NULL"), nullable=True
    )
    tag_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="SET NULL"), nullable=True
    )
    podcast_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("podcasts.id", ondelete="SET NULL"), nullable=True
    )
    #: 'playlist', 'track', 'stream' or 'podcast'
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Measured listening time; NULL means "no reliable figure", counted as 0.
    listened_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TagScanEvent(Base):
    """One RFID scan attempt - played, blocked or unassigned (issue #72)."""

    __tablename__ = "tag_scan_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tag_uid: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tag_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    # The history is always read newest-first.
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, nullable=False, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<TagScanEvent(id={self.id}, tag_uid={self.tag_uid!r}, "
            f"action={self.action!r}, scanned_at={self.scanned_at})>"
        )


class Tag(Base):
    """RFID tag to content mapping."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tag_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Nullable so a card can exist without content - the "unassigned" filter in
    # the WebUI relies on it.
    content_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    content_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=_now, nullable=True
    )
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: Blocked card: scanning it reports tag_blocked instead of playing.
    disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    def __repr__(self) -> str:
        return (
            f"<Tag(id={self.id}, tag_id={self.tag_id}, "
            f"content_type={self.content_type}, content_id={self.content_id}, "
            f"disabled={self.disabled})>"
        )


class Playlist(Base):
    """Audio playlist."""

    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cover_art_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=_now, nullable=True
    )

    tracks: Mapped[list["PlaylistTrack"]] = relationship(
        "PlaylistTrack", back_populates="playlist", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Playlist(id={self.id}, name={self.name})>"


class StreamFolder(Base):
    """Logical folder to group streams in the media library."""

    __tablename__ = "stream_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stream_folders.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=_now, nullable=True
    )

    children: Mapped[list["StreamFolder"]] = relationship(
        "StreamFolder", back_populates="parent"
    )
    parent: Mapped["StreamFolder | None"] = relationship(
        "StreamFolder", back_populates="children", remote_side="StreamFolder.id"
    )

    def __repr__(self) -> str:
        return f"<StreamFolder(id={self.id}, name={self.name}, parent_id={self.parent_id})>"


class Stream(Base):
    """Audio stream (e.g. web radio). Not part of playlists."""

    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    cover_art_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    folder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stream_folders.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    folder: Mapped["StreamFolder | None"] = relationship(
        "StreamFolder", foreign_keys=[folder_id]
    )

    def __repr__(self) -> str:
        return f"<Stream(id={self.id}, title={self.title})>"


class TrackFolder(Base):
    """Logical folder to group tracks in the media library."""

    __tablename__ = "track_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("track_folders.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=_now, nullable=True
    )

    children: Mapped[list["TrackFolder"]] = relationship(
        "TrackFolder", back_populates="parent"
    )
    parent: Mapped["TrackFolder | None"] = relationship(
        "TrackFolder", back_populates="children", remote_side="TrackFolder.id"
    )

    def __repr__(self) -> str:
        return f"<TrackFolder(id={self.id}, name={self.name}, parent_id={self.parent_id})>"


class Track(Base):
    """Audio track (file or remote). Used in playlists."""

    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str | None] = mapped_column(String(255), nullable=True)
    album: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    cover_art_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    folder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("track_folders.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    folder: Mapped["TrackFolder | None"] = relationship(
        "TrackFolder", foreign_keys=[folder_id]
    )

    def __repr__(self) -> str:
        return (
            f"<Track(id={self.id}, title={self.title}, "
            f"source_type={self.source_type}, folder_id={self.folder_id})>"
        )


class PlaylistTrack(Base):
    """Many-to-many relationship between playlists and tracks with ordering."""

    __tablename__ = "playlist_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    playlist: Mapped["Playlist"] = relationship("Playlist", back_populates="tracks")
    track: Mapped["Track"] = relationship("Track")

    __table_args__ = (
        UniqueConstraint("playlist_id", "position", name="unique_playlist_position"),
    )

    def __repr__(self) -> str:
        return (
            f"<PlaylistTrack(playlist_id={self.playlist_id}, "
            f"track_id={self.track_id}, position={self.position})>"
        )


class PodcastFolder(Base):
    """Logical folder to group podcasts in the media library."""

    __tablename__ = "podcast_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("podcast_folders.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=_now, nullable=True
    )

    children: Mapped[list["PodcastFolder"]] = relationship(
        "PodcastFolder", back_populates="parent"
    )
    parent: Mapped["PodcastFolder | None"] = relationship(
        "PodcastFolder", back_populates="children", remote_side="PodcastFolder.id"
    )

    def __repr__(self) -> str:
        return f"<PodcastFolder(id={self.id}, name={self.name}, parent_id={self.parent_id})>"


class Podcast(Base):
    """Podcast feed (RSS)."""

    __tablename__ = "podcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    rss_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    cover_art_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    folder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("podcast_folders.id", ondelete="SET NULL"), nullable=True
    )
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    folder: Mapped["PodcastFolder | None"] = relationship(
        "PodcastFolder", foreign_keys=[folder_id]
    )

    def __repr__(self) -> str:
        return f"<Podcast(id={self.id}, title={self.title})>"


class PodcastEpisode(Base):
    """Single episode of a podcast."""

    __tablename__ = "podcast_episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    podcast_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("podcasts.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    guid: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("podcast_id", "source_uri", name="uq_podcast_episode_uri"),
    )

    def __repr__(self) -> str:
        return (
            f"<PodcastEpisode(id={self.id}, podcast_id={self.podcast_id}, "
            f"title={self.title})>"
        )


class TemperatureReading(Base):
    """One system temperature sample (e.g. Raspberry Pi CPU) for analytics."""

    __tablename__ = "temperature_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Read as a time range by the history endpoint.
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    temperature_celsius: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<TemperatureReading(id={self.id}, recorded_at={self.recorded_at}, "
            f"temperature_celsius={self.temperature_celsius})>"
        )


class TrackResumePosition(Base):
    """Persisted playback resume position per content URI."""

    __tablename__ = "track_resume_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_uri: Mapped[str] = mapped_column(
        String(1024), nullable=False, unique=True, index=True
    )
    position_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<TrackResumePosition("
            f"source_uri={self.source_uri!r}, "
            f"position_ms={self.position_ms}, "
            f"content_type={self.content_type!r})>"
        )
