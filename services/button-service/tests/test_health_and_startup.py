"""/health has to distinguish "configured" from "actually working".

A pin another service owns, or a buttons.json the schema rejects, both leave a
box whose buttons do nothing. Both used to report ``healthy``.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from button_service.config_schema import AppConfig, EnvConfig
from button_service.main import ButtonService
from button_service.models import HealthState
from fastapi.testclient import TestClient

from button_test_doubles import FakePinRegistry, install_fake_gpio, push


# --------------------------------------------------------------------------
# HealthState
# --------------------------------------------------------------------------


def test_all_buttons_up_is_healthy():
    assert HealthState(buttons_configured=3, buttons_available=3, gpio_enabled=True).buttons_usable


def test_no_buttons_configured_is_healthy():
    assert HealthState(buttons_configured=0, buttons_available=0, gpio_enabled=True).buttons_usable


def test_a_single_dead_button_is_degraded():
    state = HealthState(buttons_configured=3, buttons_available=2, gpio_enabled=True)
    assert not state.buttons_usable


def test_every_button_dead_is_degraded():
    state = HealthState(buttons_configured=3, buttons_available=0, gpio_enabled=True)
    assert not state.buttons_usable


def test_disable_gpio_is_a_setting_not_a_fault():
    state = HealthState(buttons_configured=3, buttons_available=0, gpio_enabled=False)
    assert state.buttons_usable


def test_an_unloadable_config_is_degraded():
    state = HealthState(
        buttons_configured=0,
        buttons_available=0,
        gpio_enabled=True,
        config_error="Invalid JSON",
    )
    assert not state.buttons_usable


# --------------------------------------------------------------------------
# Service startup
# --------------------------------------------------------------------------


def _app_config(tmp_path, *, disable_gpio: bool = False) -> AppConfig:
    return AppConfig(
        env=EnvConfig(
            mqtt_broker="mqtt",
            mqtt_port=1883,
            minabox_device_id="box1",
            log_level="INFO",
            disable_gpio=disable_gpio,
        )
    )


def _service(tmp_path, config_text: str, *, disable_gpio: bool = False) -> ButtonService:
    path = tmp_path / "buttons.json"
    path.write_text(config_text, encoding="utf-8")
    service = ButtonService(_app_config(tmp_path, disable_gpio=disable_gpio))
    service.config_manager._config_path = path
    return service


VALID = json.dumps(
    {
        "buttons": [
            {"id": "a", "name": "A", "mode": "basic", "type": "push", "gpio": 5, "action": "next"}
        ]
    }
)

# A push button without a GPIO pin. The WebUI could produce exactly this, and
# the backend wrote it through because it only checked that "buttons" is a list.
INVALID = json.dumps(
    {"buttons": [{"id": "a", "name": "A", "mode": "basic", "type": "push", "action": "next"}]}
)


def test_valid_config_loads(tmp_path):
    service = _service(tmp_path, VALID)
    assert service._load_buttons_config().buttons[0].id == "a"
    assert service._config_error is None


def test_broken_config_starts_empty_instead_of_killing_the_process(tmp_path):
    """This used to raise out of main() -- with restart: unless-stopped, a loop."""
    service = _service(tmp_path, INVALID)

    config = service._load_buttons_config()

    assert config.buttons == []
    assert service._config_error is not None


def test_broken_config_shows_up_on_health(tmp_path):
    service = _service(tmp_path, INVALID)
    service._load_buttons_config()

    state = service._get_health_state()

    assert state.buttons_configured == 0
    assert not state.buttons_usable


def test_broken_config_is_not_written_back(tmp_path):
    """Falling back to empty must not overwrite what the user has to repair."""
    path = tmp_path / "buttons.json"
    service = _service(tmp_path, INVALID)
    service._load_buttons_config()

    assert json.loads(path.read_text()) == json.loads(INVALID)


def test_health_endpoint_reports_a_dead_pin(tmp_path, monkeypatch):
    """End to end: one configured button, its pin busy -> degraded."""
    registry = FakePinRegistry(busy={5})
    install_fake_gpio(monkeypatch, registry)

    service = _service(tmp_path, VALID)

    async def bring_up() -> None:
        service._start_gpio(service._load_buttons_config())

    asyncio.run(bring_up())

    monkeypatch.setattr(type(service.mqtt_client), "is_connected", property(lambda self: True))
    app = __import__(
        "button_service.api.routes", fromlist=["create_app"]
    ).create_app(service.config, service.mqtt_client, get_health_state=service._get_health_state)

    body = TestClient(app).get("/health").json()

    assert body["status"] == "degraded"
    assert body["buttons_configured"] == 1
    assert body["buttons_available"] == 0
    assert body["mqtt_connected"] is True


def test_health_endpoint_is_healthy_when_the_pin_comes_up(tmp_path, monkeypatch):
    registry = FakePinRegistry()
    install_fake_gpio(monkeypatch, registry)

    service = _service(tmp_path, VALID)

    async def bring_up() -> None:
        service._start_gpio(service._load_buttons_config())

    asyncio.run(bring_up())

    monkeypatch.setattr(type(service.mqtt_client), "is_connected", property(lambda self: True))
    app = __import__(
        "button_service.api.routes", fromlist=["create_app"]
    ).create_app(service.config, service.mqtt_client, get_health_state=service._get_health_state)

    body = TestClient(app).get("/health").json()

    assert body["status"] == "healthy"
    assert body["buttons_available"] == 1
    assert body["config_error"] is None
    service._gpio_manager.close()


@pytest.mark.parametrize("disable_gpio", [True, False])
def test_disable_gpio_skips_the_hardware_entirely(tmp_path, monkeypatch, disable_gpio):
    registry = FakePinRegistry()
    install_fake_gpio(monkeypatch, registry)

    service = _service(tmp_path, VALID, disable_gpio=disable_gpio)

    async def bring_up() -> None:
        service._start_gpio(service._load_buttons_config())

    asyncio.run(bring_up())

    if disable_gpio:
        assert service._gpio_manager is None
        assert registry.held == set()
        assert service._get_health_state().buttons_usable
    else:
        assert registry.held == {5}
        service._gpio_manager.close()
