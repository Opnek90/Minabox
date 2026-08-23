"""Baseline: the schema as it stood before revision 0001.

Revisions 0001-0005 assume these tables already exist. Until now they did,
because `Base.metadata.create_all()` ran first on every start - which is also
why 0001 could never succeed on a fresh install and left `alembic_version`
empty for good. With create_all gone from the normal path, the chain needs its
own starting point, and this is it.

Deliberately raw DDL rather than model-derived: a migration has to keep
describing the schema of its own time even after the models have moved on.

Revision ID: 0000
Revises: (initial)
"""

from __future__ import annotations

from alembic import op

revision: str = "0000"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE playlists (
	id INTEGER NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description VARCHAR(1000), 
	cover_art_url VARCHAR(512), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
)
        """
    )

    op.execute(
        """
CREATE TABLE podcasts (
	id INTEGER NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	rss_url VARCHAR(1024) NOT NULL, 
	description VARCHAR(2000), 
	cover_art_url VARCHAR(512), 
	last_fetched_at DATETIME, 
	last_played_at DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)
        """
    )

    op.execute(
        """
CREATE TABLE streams (
	id INTEGER NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	artist VARCHAR(255), 
	source_uri VARCHAR(1024) NOT NULL, 
	cover_art_url VARCHAR(512), 
	created_at DATETIME NOT NULL, 
	last_played_at DATETIME, 
	PRIMARY KEY (id)
)
        """
    )

    op.execute(
        """
CREATE TABLE tag_scan_events (
	id INTEGER NOT NULL, 
	tag_uid VARCHAR(32) NOT NULL, 
	tag_name VARCHAR(255), 
	media_title VARCHAR(512), 
	media_type VARCHAR(16), 
	action VARCHAR(16) NOT NULL, 
	scanned_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)
        """
    )

    op.execute(
        """
CREATE INDEX ix_tag_scan_events_tag_uid ON tag_scan_events (tag_uid)
        """
    )

    op.execute(
        """
CREATE TABLE tags (
	id INTEGER NOT NULL, 
	tag_id VARCHAR(32) NOT NULL, 
	name VARCHAR(255), 
	content_type VARCHAR(16) NOT NULL, 
	content_id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME, 
	last_scanned_at DATETIME, 
	PRIMARY KEY (id)
)
        """
    )

    op.execute(
        """
CREATE UNIQUE INDEX ix_tags_tag_id ON tags (tag_id)
        """
    )

    op.execute(
        """
CREATE TABLE temperature_readings (
	id INTEGER NOT NULL, 
	recorded_at DATETIME NOT NULL, 
	temperature_celsius FLOAT NOT NULL, 
	PRIMARY KEY (id)
)
        """
    )

    op.execute(
        """
CREATE TABLE tracks (
	id INTEGER NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	artist VARCHAR(255), 
	album VARCHAR(255), 
	duration_ms INTEGER, 
	source_type VARCHAR(16) NOT NULL, 
	source_uri VARCHAR(1024) NOT NULL, 
	cover_art_url VARCHAR(512), 
	created_at DATETIME NOT NULL, 
	last_played_at DATETIME, 
	PRIMARY KEY (id)
)
        """
    )

    op.execute(
        """
CREATE TABLE playback_events (
	id INTEGER NOT NULL, 
	started_at DATETIME NOT NULL, 
	ended_at DATETIME, 
	track_id INTEGER, 
	stream_id INTEGER, 
	playlist_id INTEGER, 
	tag_id INTEGER, 
	podcast_id INTEGER, 
	content_type VARCHAR(16) NOT NULL, 
	listened_ms INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(track_id) REFERENCES tracks (id) ON DELETE SET NULL, 
	FOREIGN KEY(podcast_id) REFERENCES podcasts (id) ON DELETE SET NULL, 
	FOREIGN KEY(playlist_id) REFERENCES playlists (id) ON DELETE SET NULL, 
	FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE SET NULL, 
	FOREIGN KEY(stream_id) REFERENCES streams (id) ON DELETE SET NULL
)
        """
    )

    op.execute(
        """
CREATE TABLE playlist_tracks (
	id INTEGER NOT NULL, 
	playlist_id INTEGER NOT NULL, 
	track_id INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(track_id) REFERENCES tracks (id) ON DELETE CASCADE, 
	FOREIGN KEY(playlist_id) REFERENCES playlists (id) ON DELETE CASCADE, 
	CONSTRAINT unique_playlist_position UNIQUE (playlist_id, position)
)
        """
    )

    op.execute(
        """
CREATE TABLE podcast_episodes (
	id INTEGER NOT NULL, 
	podcast_id INTEGER NOT NULL, 
	title VARCHAR(512) NOT NULL, 
	source_uri VARCHAR(1024) NOT NULL, 
	guid VARCHAR(512), 
	published_at DATETIME, 
	duration_ms INTEGER, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(podcast_id) REFERENCES podcasts (id) ON DELETE CASCADE, 
	CONSTRAINT uq_podcast_episode_uri UNIQUE (podcast_id, source_uri)
)
        """
    )


def downgrade() -> None:
    op.drop_table("podcast_episodes")
    op.drop_table("playlist_tracks")
    op.drop_table("playback_events")
    op.drop_table("tracks")
    op.drop_table("temperature_readings")
    op.drop_table("tags")
    op.drop_table("tag_scan_events")
    op.drop_table("streams")
    op.drop_table("podcasts")
    op.drop_table("playlists")
