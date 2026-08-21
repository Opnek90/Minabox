"""Tests fuer den Schemastempel der Datenbank.

Die Datenbank ueberlebt jedes Update; ausgetauscht werden nur die Container.
Damit trifft neuer Code auf alte Daten - und beim Zurueckdrehen alter Code auf
neue. Der zweite Fall lief frueher stillschweigend an und liess Daten als
verschwunden erscheinen. Diese Tests halten fest, dass er jetzt erkannt wird.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend_service.core import system_alerts
from backend_service.core.db_manager import SCHEMA_VERSION, DatabaseManager


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


# ── Stempel setzen und lesen ────────────────────────────────────────────────


def test_fresh_database_is_stamped(db_path: Path) -> None:
    manager = DatabaseManager(str(db_path))
    manager.connect()

    # Eine neue Datei meldet 0 und wird auf den aktuellen Stand gehoben.
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
    """Bestehende Boxen haben keinen Stempel - sie duerfen nicht anecken."""
    manager = DatabaseManager(str(db_path))
    manager.connect()
    manager._write_schema_version(0)

    again = DatabaseManager(str(db_path))
    again.connect()

    assert again.schema_state["status"] == "migrated"
    assert again._read_schema_version() == SCHEMA_VERSION


# ── Der Fall, um den es geht ────────────────────────────────────────────────


def test_newer_database_is_detected(db_path: Path) -> None:
    """Aelterer Code auf neuerer Datenbank: erkannt statt stillschweigend."""
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
    """Der Stempel darf nicht zurueckgesetzt werden.

    Sonst haette der naechste Start keinen Anhaltspunkt mehr, und aus einer
    erkannten Lage waere wieder eine unbemerkte geworden.
    """
    first = DatabaseManager(str(db_path))
    first.connect()
    first._write_schema_version(SCHEMA_VERSION + 5)

    manager = DatabaseManager(str(db_path))
    manager.connect()

    assert manager._read_schema_version() == SCHEMA_VERSION + 5


def test_newer_database_still_connects(db_path: Path) -> None:
    """Es wird nicht abgebrochen - eine tote Box laesst sich nicht diagnostizieren."""
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


# ── Meldung an die Oberflaeche ──────────────────────────────────────────────


def test_alert_store_keeps_both_alerts() -> None:
    """Die Datenbankmeldung darf nicht von einer Temperaturwarnung verdraengt werden."""
    system_alerts.set_alert("db_schema_newer", "error", "alerts.db_schema_newer")
    system_alerts.set_alert("temperature_high", "warning", "alerts.temperature_high")

    # Der Balken zeigt eine - und zwar die schwerwiegendere.
    assert system_alerts.get_current_alert()["code"] == "db_schema_newer"
    assert len(system_alerts.get_all_alerts()) == 2

    # Kuehlt die Box ab, bleibt die Datenbankmeldung stehen.
    system_alerts.clear_alert("temperature_high")
    assert system_alerts.get_current_alert()["code"] == "db_schema_newer"
