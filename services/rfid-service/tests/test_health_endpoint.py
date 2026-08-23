"""Tests for the /health endpoint contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from rfid_test_doubles import FakeMQTT, ScriptedReader, make_config

from rfid_service.api.routes import create_app
from rfid_service.core.rfid_manager import RFIDManager


def _client(manager: RFIDManager | None, mqtt: FakeMQTT) -> TestClient:
    return TestClient(create_app(make_config(), mqtt, lambda: manager))


@pytest.fixture
def manager(mqtt: FakeMQTT) -> RFIDManager:
    return RFIDManager(make_config(), lambda: ScriptedReader(), mqtt)


def test_health_answers_before_the_manager_exists(mqtt: FakeMQTT) -> None:
    """The API starts before the reader, so /health must survive that window."""
    response = _client(None, mqtt).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["reader"]["reader_ready"] is False


def test_health_reports_degraded_while_the_reader_is_down(
    manager: RFIDManager, mqtt: FakeMQTT
) -> None:
    body = _client(manager, mqtt).get("/health").json()

    assert body["status"] == "degraded"
    assert body["mqtt_connected"] is True
    assert body["reader"]["scan_loop_alive"] is False


def test_health_reports_healthy_when_everything_runs(
    manager: RFIDManager, mqtt: FakeMQTT
) -> None:
    manager._reader = ScriptedReader(reader_id="pn532_i2c")
    manager._scan_loop_alive = True

    body = _client(manager, mqtt).get("/health").json()

    assert body["status"] == "healthy"
    assert body["reader"]["reader_id"] == "pn532_i2c"
    assert body["reader"]["mode"] == "normal"


def test_health_stays_200_when_the_broker_is_gone(
    manager: RFIDManager, mqtt: FakeMQTT
) -> None:
    """A container health check must not kill a service that is only waiting."""
    mqtt.is_connected = False

    response = _client(manager, mqtt).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_health_exposes_the_current_tag(manager: RFIDManager, mqtt: FakeMQTT) -> None:
    manager._current_tag = "AABB"

    reader_state = _client(manager, mqtt).get("/health").json()["reader"]

    assert reader_state["tag_present"] is True
    assert reader_state["tag_id"] == "AABB"
