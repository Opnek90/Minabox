"""Tests for the database schema stamp.

The database survives every update; only the containers are replaced. So new
code meets old data - and a rollback means old code meets new. The second case
used to start up silently and make data look like it had vanished. These tests
pin down that it is detected now.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend_service.core import system_alerts
from backend_service.core.db_manager import SCHEMA_VERSION, DatabaseManager


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


# ── Writing and reading the stamp ───────────────────────────────────────────


def test_fresh_database_is_stamped(db_path: Path) -> None:
    manager = DatabaseManager(str(db_path))
    manager.connect()

    # A new file reports 0 and is brought up to the current state.
    assert manager.schema_state == {
        "expected": SCHEMA_VERSION,
        "found": 0,
        "status": "migrated",
    }
    assert manager._read_schema_version() == SCHEMA_VERSION


def test_second_start_finds_nothing_to_do(db_path: Path) -> None:
    DatabaseManager(str(db_path)).connect()

    manager = DatabaseManager(str(db_path))
    manager.connect()

    assert manager.schema_state["status"] == "ok"
    assert manager.schema_state["found"] == SCHEMA_VERSION


def test_database_from_before_the_stamp_is_migrated(db_path: Path) -> None:
    """Existing boxes carry no stamp - they must not trip over that."""
    manager = DatabaseManager(str(db_path))
    manager.connect()
    manager._write_schema_version(0)

    again = DatabaseManager(str(db_path))
    again.connect()

    assert again.schema_state["status"] == "migrated"
    assert again._read_schema_version() == SCHEMA_VERSION


# ── The case this is all about ─────────────────────────────────────────────


def test_newer_database_is_detected(db_path: Path) -> None:
    """Older code on a newer database: detected instead of silent."""
    first = DatabaseManager(str(db_path))
    first.connect()
    first._write_schema_version(SCHEMA_VERSION + 5)

    manager = DatabaseManager(str(db_path))
    manager.connect()

    assert manager.schema_state == {
        "expected": SCHEMA_VERSION,
        "found": SCHEMA_VERSION + 5,
        "status": "too_new",
    }


def test_newer_database_does_not_get_downgraded(db_path: Path) -> None:
    """The stamp must not be reset.

    Otherwise the next start would have nothing to go on, and a detected
    situation would turn back into an unnoticed one.
    """
    first = DatabaseManager(str(db_path))
    first.connect()
    first._write_schema_version(SCHEMA_VERSION + 5)

    manager = DatabaseManager(str(db_path))
    manager.connect()

    assert manager._read_schema_version() == SCHEMA_VERSION + 5


def test_newer_database_still_connects(db_path: Path) -> None:
    """It does not abort - a dead box cannot be diagnosed."""
    first = DatabaseManager(str(db_path))
    first.connect()
    first._write_schema_version(SCHEMA_VERSION + 1)

    manager = DatabaseManager(str(db_path))
    manager.connect()

    session = manager.get_session()
    try:
        assert session is not None
    finally:
        session.close()


# ── What the WebUI is told ─────────────────────────────────────────────────


def test_alert_store_keeps_both_alerts() -> None:
    """A temperature warning must not displace the database notice."""
    system_alerts.set_alert("db_schema_newer", "error", "alerts.db_schema_newer")
    system_alerts.set_alert("temperature_high", "warning", "alerts.temperature_high")

    # The bar shows one - and it is the more severe one.
    assert system_alerts.get_current_alert()["code"] == "db_schema_newer"
    assert len(system_alerts.get_all_alerts()) == 2

    # Once the box cools down, the database notice stays.
    system_alerts.clear_alert("temperature_high")
    assert system_alerts.get_current_alert()["code"] == "db_schema_newer"
