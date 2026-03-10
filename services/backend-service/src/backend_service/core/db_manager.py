"""Database manager for Backend Service."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend_service.models.database import Base, PlaybackEvent, PlaylistTrack, Stream, Track

logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Manages database connection and sessions."""

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.engine: Engine | None = None
        self.SessionLocal: sessionmaker | None = None
        logger.debug("db_manager_initialized", database_path=str(self.database_path))

    def connect(self) -> None:
        """Connect to database and create tables if needed."""
        logger.debug("db_connecting", path=str(self.database_path))

        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        database_url = f"sqlite:///{self.database_path}"
        self.engine = create_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30.0},
        )

        @event.listens_for(Engine, "connect")
        def set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.close()

        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

        Base.metadata.create_all(bind=self.engine)
        self._apply_column_migrations()
        self._migrate_stream_tracks_to_streams()

        # fix #58: close any orphaned open PlaybackEvents from a previous unclean shutdown
        self._close_orphaned_playback_events()

        logger.debug("db_connected_successfully", database_url=database_url)

    def _close_orphaned_playback_events(self) -> None:
        """Close any PlaybackEvents that were left open by an unclean shutdown.

        The periodic flush (every 60s) already wrote the best-known listened_ms
        to the DB. We just need to set ended_at = now so the event is counted
        in stats. At most 60s of play time is lost per unclean shutdown.

        Events with listened_ms = NULL are closed with listened_ms = 0 — they
        represent sessions that ended before the first flush (< 60s played).
        """
        session = self.get_session()
        try:
            open_events = (
                session.query(PlaybackEvent)
                .filter(PlaybackEvent.ended_at.is_(None))
                .all()
            )
            if not open_events:
                return
            now = datetime.now(UTC)
            for ev in open_events:
                ev.ended_at = now
                # listened_ms already set by periodic flush; if NULL treat as 0
                if ev.listened_ms is None:
                    ev.listened_ms = 0
            session.commit()
            logger.info(
                "startup_cleanup_closed_orphaned_events",
                count=len(open_events),
                event_ids=[e.id for e in open_events],
            )
        except Exception as exc:
            session.rollback()
            logger.warning("startup_cleanup_failed", error=str(exc))
        finally:
            session.close()

    def _apply_column_migrations(self) -> None:
        """Add new nullable columns to existing tables (idempotent ALTER TABLE)."""
        migrations = [
            ("tags",      "last_scanned_at",  "DATETIME"),
            ("tracks",    "last_played_at",    "DATETIME"),
            ("playlists", "cover_art_url",     "VARCHAR(512)"),
            ("tracks",    "cover_art_url",     "VARCHAR(512)"),
            ("playback_events", "podcast_id",   "INTEGER"),
            ("podcasts",       "last_played_at", "DATETIME"),
            ("streams",        "cover_art_url",  "VARCHAR(512)"),
            ("playback_events", "listened_ms",   "INTEGER"),
        ]
        with self.engine.connect() as conn:
            for table, column, col_type in migrations:
                try:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                        )
                    )
                    conn.commit()
                    logger.debug("db_column_added", table=table, column=column)
                except Exception:
                    pass

    def _migrate_stream_tracks_to_streams(self) -> None:
        """One-time migration: move rows with source_type='stream' from tracks to streams."""
        session = self.get_session()
        try:
            stream_tracks = (
                session.query(Track)
                .filter(Track.source_type == "stream")
                .all()
            )
            if not stream_tracks:
                return
            stream_ids = [t.id for t in stream_tracks]
            session.query(PlaylistTrack).filter(
                PlaylistTrack.track_id.in_(stream_ids)
            ).delete(synchronize_session=False)
            for t in stream_tracks:
                session.add(
                    Stream(
                        title=t.title,
                        artist=t.artist,
                        source_uri=t.source_uri,
                        created_at=t.created_at,
                        last_played_at=t.last_played_at,
                    )
                )
            session.commit()
            session.query(Track).filter(Track.source_type == "stream").delete(
                synchronize_session=False
            )
            session.commit()
            logger.info(
                "db_streams_migrated",
                count=len(stream_tracks),
                track_ids=stream_ids,
            )
        except Exception as e:
            session.rollback()
            logger.warning("db_stream_migration_skipped", error=str(e))
        finally:
            session.close()

    def disconnect(self) -> None:
        """Disconnect from database."""
        if self.engine:
            logger.info("db_disconnecting")
            self.engine.dispose()
            self.engine = None
            self.SessionLocal = None
            logger.info("db_disconnected")

    def get_session(self) -> Session:
        if self.SessionLocal is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self.SessionLocal()

    def is_connected(self) -> bool:
        if self.engine is None:
            return False
        try:
            with self.engine.connect() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error("db_connection_check_failed", error=str(e))
            return False

    def run_migrations(self) -> None:
        logger.debug("db_running_migrations")
        try:
            from alembic.config import Config
            from alembic import command
            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option(
                "sqlalchemy.url", f"sqlite:///{self.database_path}"
            )
            command.upgrade(alembic_cfg, "head")
            logger.debug("db_migrations_completed")
        except Exception as e:
            logger.error("db_migrations_failed", error=str(e))
            raise


# Global database manager instance
db_manager: DatabaseManager | None = None


def init_db(database_path: str) -> DatabaseManager:
    global db_manager
    db_manager = DatabaseManager(database_path)
    db_manager.connect()
    return db_manager


def get_db() -> Session:
    if db_manager is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()
