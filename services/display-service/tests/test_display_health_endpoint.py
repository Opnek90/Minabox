"""Tests for the /health contract, and for POST /test.

The container health check only asks whether this endpoint answers at all, and
the backend only reads the body for a version. So `status` is not what keeps the
container alive -- it is what tells a human why the panel is dark.

It used to derive that from the broker connection alone: a panel that never
answered on the I2C bus reported "healthy" for as long as MQTT was up, which is
the one thing somebody looking at a blank display would be asking about.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from display_service.api.routes import create_app
from display_service.config_manager import ConfigManager
from display_service.config_schema import DisplayServiceConfig


class FakeMQTT:
    def __init__(self, connected: bool = True) -> None:
        self.is_connected = connected


class FakeService:
    def __init__(self, test_pattern: bool = True) -> None:
        self.test_pattern = test_pattern
        self.calls = 0

    async def show_test_pattern(self) -> bool:
        self.calls += 1
        return self.test_pattern


def _client(
    app_config,
    *,
    connected: bool = True,
    available: bool = True,
    enabled: bool = True,
    loaded: bool = True,
    service=None,
    monkeypatch=None,
) -> TestClient:
    monkeypatch.setattr("display_service.api.routes.is_available", lambda: available)
    manager = ConfigManager()
    if loaded:
        manager._current_config = DisplayServiceConfig(enabled=enabled, elements=[])
    return TestClient(create_app(app_config, manager, FakeMQTT(connected), service))


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_healthy_when_the_broker_and_the_panel_are_there(app_config, monkeypatch):
    body = _client(app_config, monkeypatch=monkeypatch).get("/health").json()

    assert body["status"] == "healthy"
    assert body["display_enabled"] is True
    assert body["display_available"] is True
    assert body["mqtt_connected"] is True
    assert body["service"] == "display"
    assert body["device_id"] == "box1"


def test_degraded_while_the_broker_is_away(app_config, monkeypatch):
    body = (
        _client(app_config, connected=False, monkeypatch=monkeypatch)
        .get("/health")
        .json()
    )

    assert body["status"] == "degraded"
    assert body["mqtt_connected"] is False


def test_degraded_when_the_panel_never_answered(app_config, monkeypatch):
    """The wrong I2C address used to look perfectly healthy."""
    body = (
        _client(app_config, available=False, monkeypatch=monkeypatch)
        .get("/health")
        .json()
    )

    assert body["status"] == "degraded"
    assert body["display_enabled"] is True
    assert body["display_available"] is False


def test_a_deliberately_disabled_display_stays_healthy(app_config, monkeypatch):
    """Switched off is a choice, not a fault -- it must not read as degraded."""
    body = (
        _client(app_config, enabled=False, available=False, monkeypatch=monkeypatch)
        .get("/health")
        .json()
    )

    assert body["status"] == "healthy"
    assert body["display_enabled"] is False


def test_no_config_loaded_yet_is_not_reported_as_a_working_display(
    app_config, monkeypatch
):
    body = (
        _client(app_config, loaded=False, monkeypatch=monkeypatch).get("/health").json()
    )

    assert body["display_enabled"] is False


def test_health_answers_200_even_while_degraded(app_config, monkeypatch):
    """A restart would fix neither a dead broker nor a missing panel."""
    response = _client(
        app_config, connected=False, available=False, monkeypatch=monkeypatch
    ).get("/health")

    assert response.status_code == 200


def test_health_reports_the_build_version(app_config, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    body = _client(app_config, monkeypatch=monkeypatch).get("/health").json()

    assert body["version"] == "1.2.3"


# ---------------------------------------------------------------------------
# POST /test
# ---------------------------------------------------------------------------


def test_the_test_endpoint_reports_success(app_config, monkeypatch):
    service = FakeService(test_pattern=True)
    response = _client(app_config, service=service, monkeypatch=monkeypatch).post(
        "/test"
    )

    assert response.status_code == 200
    assert response.json() == {"tested": True}
    assert service.calls == 1


def test_the_test_endpoint_404s_without_a_panel(app_config, monkeypatch):
    """So the setup wizard can say so instead of claiming a successful test."""
    service = FakeService(test_pattern=False)
    response = _client(app_config, service=service, monkeypatch=monkeypatch).post(
        "/test"
    )

    assert response.status_code == 404


def test_the_test_endpoint_503s_before_the_service_is_wired_up(app_config, monkeypatch):
    response = _client(app_config, service=None, monkeypatch=monkeypatch).post("/test")

    assert response.status_code == 503


@pytest.mark.parametrize("path", ["/health", "/test"])
def test_the_service_exposes_nothing_else(app_config, monkeypatch, path):
    """Two endpoints, both unauthenticated - the surface must stay this small."""
    client = _client(app_config, monkeypatch=monkeypatch)
    routes = {r.path for r in client.app.routes if r.path.startswith("/")}

    assert path in routes
    assert routes - {"/health", "/test"} <= {
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
