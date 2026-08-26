"""Shared fixtures: a DisplayService that never touches hardware or a broker.

Constructing one is cheap and side-effect free -- the MQTT client only records
its subscriptions until start() is called, and the panel is only opened from
start() too. So the render logic can be tested exactly as it runs.
"""

from __future__ import annotations

import pytest

from display_service.config_schema import (
    AppConfig,
    DisplayServiceConfig,
    EnvConfig,
)
from display_service.main import DisplayService


@pytest.fixture
def app_config() -> AppConfig:
    return AppConfig(
        env=EnvConfig(
            mqtt_broker="mqtt",
            mqtt_port=1883,
            minabox_device_id="box1",
            log_level="INFO",
        )
    )


@pytest.fixture
def service(app_config: AppConfig) -> DisplayService:
    return DisplayService(app_config)


@pytest.fixture
def configure(service: DisplayService):
    """Give the service a display config built from element tuples."""

    def _configure(*elements, **overrides) -> DisplayServiceConfig:
        cfg = DisplayServiceConfig(elements=list(elements), **overrides)
        service._display_config = cfg
        return cfg

    return _configure
