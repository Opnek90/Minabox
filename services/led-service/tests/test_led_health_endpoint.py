"""Tests for the /health contract.

The container health check only asks whether this endpoint answers at all, and
the backend only reads the body for a version. So `status` is not what keeps
the container alive -- it is what tells a human why the LEDs are dark.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from led_test_doubles import FakeMQTT, make_config, make_led

from led_service.api.routes import create_app
from led_service.core import LEDManager


async def _manager(*configs, available: bool) -> LEDManager:
    manager = LEDManager(disable_gpio=True)
    await manager.initialize_leds(list(configs))
    for controller in manager._controllers.values():
        controller._gpio_available = available
    return manager


def _client(manager: LEDManager, mqtt: FakeMQTT) -> TestClient:
    return TestClient(create_app(make_config(), manager, mqtt))


@pytest.mark.asyncio
async def test_healthy_when_the_broker_and_the_leds_are_there() -> None:
    manager = await _manager(make_led("led_1"), available=True)

    body = _client(manager, FakeMQTT()).get("/health").json()

    assert body["status"] == "healthy"
    assert body["leds_configured"] == 1
    assert body["leds_available"] == 1


@pytest.mark.asyncio
async def test_degraded_while_the_broker_is_away() -> None:
    manager = await _manager(make_led("led_1"), available=True)

    body = _client(manager, FakeMQTT(connected=False)).get("/health").json()

    assert body["status"] == "degraded"
    assert body["mqtt_connected"] is False


@pytest.mark.asyncio
async def test_degraded_when_no_configured_led_holds_a_pin() -> None:
    """A wrong GPIO group id used to look perfectly healthy."""
    manager = await _manager(make_led("led_1"), make_led("led_2"), available=False)

    body = _client(manager, FakeMQTT()).get("/health").json()

    assert body["status"] == "degraded"
    assert body["leds_configured"] == 2
    assert body["leds_available"] == 0


@pytest.mark.asyncio
async def test_a_box_without_leds_is_not_degraded() -> None:
    """Nothing configured is a choice, not a fault."""
    manager = await _manager(available=False)

    body = _client(manager, FakeMQTT()).get("/health").json()

    assert body["status"] == "healthy"
    assert body["leds_configured"] == 0


@pytest.mark.asyncio
async def test_health_answers_even_with_everything_broken() -> None:
    """The endpoint has to stay reachable; that is what the container checks."""
    manager = await _manager(make_led("led_1"), available=False)

    response = _client(manager, FakeMQTT(connected=False)).get("/health")

    assert response.status_code == 200
