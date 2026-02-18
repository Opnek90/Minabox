"""Database manager for Backend Service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend_service.models.database import Base

logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Manages database connection and sessions."""

    def __init__(self, database_path: str) -> None:
        """Initialize database manager.

        Args:
            database_path: Path to SQLite database file
        """
        self.database_path = Path(database_path)
        self.engine: Engine | None = None
        self.SessionLocal: sessionmaker | None = None
        logger.info("db_manager_initialized", database_path=str(self.database_path))

    def connect(self) -> None:
        """Connect to database and create tables if needed."""
        logger.info("db_connecting", path=str(self.database_path))

        # Ensure database directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        # Create engine
        database_url = f"sqlite:///{self.database_path}"
        self.engine = create_engine(
            database_url,
            echo=False,  # Set to True for SQL query logging
            connect_args={"check_same_thread": False},  # Needed for SQLite with FastAPI
        )

        # Enable foreign keys for SQLite
        @event.listens_for(Engine, "connect")
        def set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

        # Create tables for any models not yet in the DB
        Base.metadata.create_all(bind=self.engine)

        # Add columns introduced after initial schema (idempotent)
        self._apply_column_migrations()

        logger.info("db_connected_successfully", database_url=database_url)

    def _apply_column_migrations(self) -> None:
        """Add new nullable columns to existing tables (idempotent ALTER TABLE)."""
        migrations = [
            ("tags",      "last_scanned_at",  "DATETIME"),
            ("tracks",    "last_played_at",    "DATETIME"),
            ("playlists", "cover_art_url",     "VARCHAR(512)"),
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
                    logger.info("db_column_added", table=table, column=column)
                except Exception:
                    # Column already exists – silently skip
                    pass

    def disconnect(self) -> None:
        """Disconnect from database."""
        if self.engine:
            logger.info("db_disconnecting")
            self.engine.dispose()
            self.engine = None
            self.SessionLocal = None
            logger.info("db_disconnected")

    def get_session(self) -> Session:
        """Get a new database session.

        Returns:
            SQLAlchemy session

        Raises:
            RuntimeError: If database not connected
        """
        if self.SessionLocal is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self.SessionLocal()

    def is_connected(self) -> bool:
        """Check if database is connected.

        Returns:
            True if connected, False otherwise
        """
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
        """Run Alembic migrations to latest version.

        This should be called on service startup to ensure DB schema is up-to-date.
        """
        logger.info("db_running_migrations")
        try:
            from alembic.config import Config

            from alembic import command

            # Load Alembic config
            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option(
                "sqlalchemy.url", f"sqlite:///{self.database_path}"
            )

            # Run migrations
            command.upgrade(alembic_cfg, "head")
            logger.info("db_migrations_completed")
        except Exception as e:
            logger.error("db_migrations_failed", error=str(e))
            raise


# Global database manager instance
db_manager: DatabaseManager | None = None


def init_db(database_path: str) -> DatabaseManager:
    """Initialize global database manager.

    Args:
        database_path: Path to SQLite database file

    Returns:
        Initialized DatabaseManager instance
    """
    global db_manager
    db_manager = DatabaseManager(database_path)
    db_manager.connect()
    return db_manager


def get_db() -> Session:
    """Get database session for dependency injection.

    Yields:
        SQLAlchemy session
    """
    if db_manager is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()
