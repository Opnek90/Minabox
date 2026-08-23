"""Alembic owns the schema - these tests are what makes that safe to claim.

Three populations have to end up with the same database:

* a fresh install, built by the migration chain alone,
* a box that has been running for months, stamped at the latest revision,
* a box installed while revision 0001 could never succeed, whose
  `alembic_version` table exists but is empty.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine

from backend_service.core.db_manager import (
    ADOPTION_REVISION,
    SERVICE_ROOT,
    DatabaseManager,
)
from backend_service.models.database import Base


def _head_revision() -> str:
    """Ask Alembic for head rather than hardcoding it - one less thing to rot."""
    from alembic.script import ScriptDirectory

    return ScriptDirectory(str(SERVICE_ROOT / "alembic")).get_current_head()


def _stamped_revision(path) -> str | None:
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        return rows[0][0] if rows else None
    finally:
        conn.close()


def _schema(path) -> dict[str, object]:
    """Tables, their columns and their indexes, as SQLite itself reports them."""
    conn = sqlite3.connect(str(path))
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
            )
        ]
        columns = {
            table: sorted(
                (row[1], row[2].upper(), row[3])  # name, type, not-null
                for row in conn.execute(f"PRAGMA table_info({table})")
            )
            for table in sorted(tables)
        }
        # Indexes matter as much as columns here: revision 0006 adds them, and
        # without comparing them the test would happily pass on a chain that
        # forgot half of what the models declare.
        indexes = sorted(
            (row[0], row[1])
            for row in conn.execute(
                "SELECT name, tbl_name FROM sqlite_master WHERE type='index' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        )
        return {"columns": columns, "indexes": indexes}
    finally:
        conn.close()


def _connect(tmp_path, name: str) -> DatabaseManager:
    manager = DatabaseManager(str(tmp_path / name))
    manager.connect()
    return manager


def test_the_migration_chain_builds_what_the_models_describe(tmp_path):
    """The baseline plus every revision must equal create_all().

    Without this the chain could drift from the models and nobody would find
    out until a fresh install hit a missing column in production.
    """
    migrated = _connect(tmp_path, "migrated.db")
    migrated.disconnect()

    reference = tmp_path / "reference.db"
    engine = create_engine(f"sqlite:///{reference}")
    Base.metadata.create_all(bind=engine)
    engine.dispose()

    assert _schema(tmp_path / "migrated.db") == _schema(reference)


def test_a_fresh_database_ends_up_stamped_at_head(tmp_path):
    manager = _connect(tmp_path, "fresh.db")
    manager.disconnect()

    assert _stamped_revision(tmp_path / "fresh.db") == _head_revision()


def test_a_database_left_unstamped_is_adopted_not_replayed(tmp_path):
    """The state every install created while revision 0001 kept failing.

    Tables present, `alembic_version` there but empty. Replaying the chain
    would fail on "table already exists" all over again; the database already
    matches the models, so it is stamped instead.
    """
    path = tmp_path / "unstamped.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    conn = sqlite3.connect(str(path))
    # Model the real thing: such a database was built by models that predate
    # revision 0006, so it has the tables but not the indexes that came later.
    for name in (
        "ix_playback_events_started_at",
        "ix_playback_events_ended_at",
        "ix_temperature_readings_recorded_at",
        "ix_tag_scan_events_scanned_at",
    ):
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
    conn.commit()
    conn.close()

    manager = DatabaseManager(str(path))
    manager.connect()
    manager.disconnect()

    # Stamped at the adoption point and then carried forward, not jumped to
    # head: everything added after that point still has to be applied.
    assert _stamped_revision(path) == _head_revision()
    assert _head_revision() != ADOPTION_REVISION, "adoption point should lag head"
    names = {name for name, _ in _schema(path)["indexes"]}
    assert "ix_playback_events_started_at" in names


def test_an_already_stamped_database_is_left_alone(tmp_path):
    """The upgrade path for a box that has been running for months."""
    first = _connect(tmp_path, "existing.db")
    first.disconnect()
    before = _schema(tmp_path / "existing.db")

    again = DatabaseManager(str(tmp_path / "existing.db"))
    again.connect()
    again.disconnect()

    assert _schema(tmp_path / "existing.db") == before


def test_connecting_twice_is_harmless(tmp_path):
    """Every restart runs this path; it has to be repeatable."""
    for _ in range(3):
        manager = _connect(tmp_path, "repeat.db")
        assert manager.schema_state["status"] in ("ok", "migrated")
        manager.disconnect()


@pytest.mark.parametrize("table", sorted(t.name for t in Base.metadata.sorted_tables))
def test_every_model_table_exists_after_a_fresh_install(tmp_path, table):
    manager = _connect(tmp_path, "complete.db")
    manager.disconnect()
    assert table in _schema(tmp_path / "complete.db")["columns"]


@pytest.mark.parametrize(
    "index",
    [
        "ix_playback_events_started_at",
        "ix_playback_events_ended_at",
        "ix_temperature_readings_recorded_at",
        "ix_tag_scan_events_scanned_at",
    ],
)
def test_the_hot_path_indexes_are_present(tmp_path, index):
    """These carry the queries that run on every stop and every scan."""
    manager = _connect(tmp_path, "indexed.db")
    manager.disconnect()
    names = {name for name, _ in _schema(tmp_path / "indexed.db")["indexes"]}
    assert index in names
