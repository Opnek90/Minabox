"""Database manager for Backend Service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import structlog
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend_service.models.database import (
    Base,
    PlaybackEvent,
    PlaylistTrack,
    Stream,
    Track,
)

logger = structlog.get_logger(__name__)

#: services/backend-service/ - alembic.ini and alembic/ sit here, and in the
#: container they land next to each other under /app. Resolved from this file
#: rather than from the working directory: `Config("alembic.ini")` only ever
#: worked because the container happens to start in /app.
SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

#: The revision a database built by the old `create_all()` path corresponds to.
#:
#: Such a database has every table the models declared at the time, so replaying
#: the chain would fail on "table already exists" - but stamping it straight to
#: head would claim later revisions had run when they had not, and their changes
#: would never reach it. It is stamped here and then upgraded normally.
ADOPTION_REVISION: Final[str] = "0005"

# Stand, den dieser Code von der Datenbank erwartet.
#
# Die Datenbank ueberlebt jedes Update - ausgetauscht werden nur die Container.
# Damit trifft neuer Code auf alte Daten, und beim Zurueckdrehen alter Code auf
# neue. Vorwaerts ist das loesbar: die Migrationen unten ergaenzen, was fehlt.
# Rueckwaerts nicht immer - _migrate_stream_tracks_to_streams etwa verschiebt
# Zeilen aus "tracks" nach "streams" und loescht sie dort. Eine Fassung von
# davor sucht Streams weiter in "tracks" und haelt sie fuer verschwunden.
#
# Diese Zahl macht den Unterschied sichtbar. Sie wird angehoben, sobald eine
# Aenderung nicht mehr rueckwaertskompatibel ist - also wenn Daten umziehen,
# Spalten oder Tabellen verschwinden oder ihre Bedeutung wechselt. Eine neue
# Spalte, die aeltere Fassungen einfach ignorieren, braucht keine Anhebung.
#
#   1 - Ausgangsstand: die Spalten aus _apply_column_migrations und der Umzug
#       der Streams. Faellt mit dem Stand zusammen, den bestehende Boxen
#       ohnehin schon haben.
SCHEMA_VERSION = 1


class DatabaseManager:
    """Manages database connection and sessions."""

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.engine: Engine | None = None
        self.SessionLocal: sessionmaker | None = None
        # Ergebnis der Schemapruefung aus connect(); von /health und
        # /system/status ausgelesen.
        self.schema_state: dict[str, Any] = {
            "expected": SCHEMA_VERSION,
            "found": None,
            "status": "unknown",
        }
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

        @event.listens_for(self.engine, "connect")
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

        self._setup_schema()

        found = self._read_schema_version()
        if found > SCHEMA_VERSION:
            # Hier laeuft aelterer Code auf einer neueren Datenbank. Genau das
            # ist der Fall, der frueher unbemerkt blieb: die Anwendung startet,
            # sucht Daten an Stellen, an die eine neuere Fassung sie nicht mehr
            # legt, und meldet sie als verschwunden.
            #
            # Es wird trotzdem nicht abgebrochen: eine Box, die gar nicht mehr
            # startet, laesst sich auch nicht mehr diagnostizieren. Stattdessen
            # wird der Zustand festgehalten und weiter oben deutlich gemeldet.
            self.schema_state = {
                "expected": SCHEMA_VERSION,
                "found": found,
                "status": "too_new",
            }
            logger.error(
                "db_schema_newer_than_code",
                found=found,
                expected=SCHEMA_VERSION,
            )
        else:
            self._apply_column_migrations()
            self._migrate_stream_tracks_to_streams()
            self._write_schema_version(SCHEMA_VERSION)
            self.schema_state = {
                "expected": SCHEMA_VERSION,
                "found": found,
                "status": "migrated" if found < SCHEMA_VERSION else "ok",
            }
            if found < SCHEMA_VERSION:
                logger.info("db_schema_migrated", was=found, now=SCHEMA_VERSION)

        # fix #58: close any orphaned open PlaybackEvents from a previous unclean shutdown
        self._close_orphaned_playback_events()

        logger.debug("db_connected_successfully", database_url=database_url)

    def _alembic_config(self) -> Any:
        from alembic.config import Config

        config = Config(str(SERVICE_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.database_path}")
        return config

    def _is_stamped(self) -> bool:
        """Whether Alembic has recorded a revision for this database."""
        try:
            with self.engine.connect() as conn:
                if not inspect(conn).has_table("alembic_version"):
                    return False
                return conn.execute(text("SELECT count(*) FROM alembic_version")).scalar() > 0
        except Exception as exc:
            logger.warning("db_alembic_state_unreadable", error=str(exc))
            return False

    def _setup_schema(self) -> None:
        """Bring the schema up to date. Alembic owns it.

        Three cases, and the middle one is why this is not a plain upgrade:

        * empty database - the baseline and every revision after it build the
          schema from nothing,
        * tables present but never stamped - a database that predates Alembic
          being usable here. `create_all()` used to run first, so revision 0001
          always failed on "table already exists" and left `alembic_version`
          empty for good. It is stamped at the revision its schema corresponds
          to, then upgraded like any other,
        * stamped - the normal path, upgrade whatever is outstanding.

        The upgrade runs in every case. Stamping straight to head instead would
        leave an adopted database permanently missing everything added after
        the adoption point.
        """
        with self.engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
        has_data_tables = bool(tables - {"alembic_version"})

        try:
            from alembic import command

            config = self._alembic_config()
            if has_data_tables and not self._is_stamped():
                command.stamp(config, ADOPTION_REVISION)
                logger.info(
                    "db_schema_adopted", tables=len(tables), revision=ADOPTION_REVISION
                )
            command.upgrade(config, "head")
            logger.debug("db_schema_upgraded")
        except Exception as exc:
            logger.error("db_migrations_failed", error=str(exc))

        self._ensure_schema_complete()

    def _ensure_schema_complete(self) -> None:
        """Last line of defence: never leave the box without its tables.

        If the migrations did not produce what the models expect - a broken
        revision, a half-applied upgrade - the box would come up unable to do
        anything at all. Creating what is missing keeps it usable and says so
        loudly, rather than failing at the first query.
        """
        with self.engine.connect() as conn:
            present = set(inspect(conn).get_table_names())
        missing = {t.name for t in Base.metadata.sorted_tables} - present
        if not missing:
            return
        logger.error("db_schema_incomplete_after_migrations", missing=sorted(missing))
        Base.metadata.create_all(bind=self.engine)
        self.schema_state["repaired"] = sorted(missing)

    def _close_orphaned_playback_events(self) -> None:
        """Close any PlaybackEvents left open by an unclean shutdown.

        ended_at is set to started_at + listened_ms so the event is assigned
        to the correct day regardless of when the service restarts.
        This avoids inflated stats when the box is off for hours before restarting.

        Events with listened_ms = NULL (crashed before first 60s flush) are
        closed with listened_ms = 0 and ended_at = started_at.
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
            for ev in open_events:
                listened = ev.listened_ms or 0
                if ev.listened_ms is None:
                    ev.listened_ms = 0
                # ended_at = when playback actually stopped (not when we restarted)
                if ev.started_at is not None:
                    ev.ended_at = ev.started_at + timedelta(milliseconds=listened)
                else:
                    ev.ended_at = datetime.now(UTC)
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

    def _read_schema_version(self) -> int:
        """Stand der Datenbank aus PRAGMA user_version.

        SQLite haelt dafuer ein Feld im Dateikopf bereit - es braucht also
        keine eigene Tabelle, und eine Datenbank aus der Zeit vor dieser
        Zaehlung liefert 0.
        """
        try:
            with self.engine.connect() as conn:
                return int(conn.execute(text("PRAGMA user_version")).scalar() or 0)
        except Exception as exc:
            logger.warning("db_schema_version_read_failed", error=str(exc))
            return 0

    def _write_schema_version(self, version: int) -> None:
        """Stand festschreiben. Erst nach erfolgreicher Migration aufrufen."""
        try:
            with self.engine.connect() as conn:
                # PRAGMA nimmt keine gebundenen Parameter; version ist eine
                # Konstante aus diesem Modul, keine Eingabe von aussen.
                conn.execute(text(f"PRAGMA user_version = {int(version)}"))
                conn.commit()
        except Exception as exc:
            logger.warning("db_schema_version_write_failed", error=str(exc))

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
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                    )
                    conn.commit()
                    logger.debug("db_column_added", table=table, column=column)
                except Exception as exc:
                    conn.rollback()
                    message = str(exc).lower()
                    if "duplicate column" in message:
                        # Expected: the column is already there.
                        continue
                    logger.warning(
                        "db_column_migration_failed",
                        table=table,
                        column=column,
                        error=str(exc),
                    )

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
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error("db_connection_check_failed", error=str(e))
            return False

    def run_migrations(self) -> None:
        """Kept for callers; the schema is set up by connect() itself now.

        Doing it inside connect() is what makes the ordering guaranteed: the
        column migrations and the stream move below both assume the tables are
        already there.
        """
        logger.debug("db_migrations_already_applied_during_connect")


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
