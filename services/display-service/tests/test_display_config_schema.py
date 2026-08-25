"""The schema is what decides whether the container starts at all.

An unloadable display.json does not degrade the service, it ends the process --
and with `restart: unless-stopped` that is a restart loop. So the shipped
template has to validate, and the rules the backend mirrors have to be the rules
that are actually here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from display_service.config import DISPLAY_CONFIG_PATH
from display_service.config_schema import (
    DisplayElement,
    DisplayServiceConfig,
    EnvConfig,
)

EXAMPLE_PATH = DISPLAY_CONFIG_PATH.with_suffix(".json.example")


# ---------------------------------------------------------------------------
# The files that ship with the service
# ---------------------------------------------------------------------------


def test_the_shipped_example_validates():
    """setup-folders.sh seeds display.json from this; a broken one bricks a box."""
    data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    DisplayServiceConfig.model_validate(data)


@pytest.mark.skipif(
    not DISPLAY_CONFIG_PATH.exists(), reason="no live config in this checkout"
)
def test_the_live_config_validates():
    data = json.loads(DISPLAY_CONFIG_PATH.read_text(encoding="utf-8"))
    DisplayServiceConfig.model_validate(data)


def test_example_and_live_config_agree_on_shape():
    """Both are seeded from the same template; a drifting example misleads."""
    if not DISPLAY_CONFIG_PATH.exists():
        pytest.skip("no live config in this checkout")
    example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    live = json.loads(DISPLAY_CONFIG_PATH.read_text(encoding="utf-8"))
    assert set(example) == set(live)


def test_the_example_stays_inside_the_area_limits():
    """Six in the header, three per column - more is dropped at render time."""
    from display_service.main import _BODY_MAX_ITEMS, _HEADER_MAX_ITEMS

    cfg = DisplayServiceConfig.model_validate(
        json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    )
    limits = {0: _HEADER_MAX_ITEMS, 1: _BODY_MAX_ITEMS, 2: _BODY_MAX_ITEMS}
    for area, limit in limits.items():
        enabled = [e for e in cfg.elements if e.enabled and e.area == area]
        assert len(enabled) <= limit, f"area {area} is overcrowded in the example"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_an_empty_config_is_valid_and_usable():
    cfg = DisplayServiceConfig()
    assert cfg.enabled is True
    assert cfg.i2c_bus == 1
    assert cfg.i2c_address == 60  # 0x3C
    assert cfg.font_size == "medium"
    assert cfg.font == "sans"
    assert cfg.elements == []


def test_an_element_needs_only_an_id_and_a_type():
    el = DisplayElement(id="x", type="clock")
    assert el.enabled is True
    assert el.order == 0
    assert el.area == 0


# ---------------------------------------------------------------------------
# What must be refused - each of these used to reach the disk
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "element",
    [
        pytest.param({"id": "x", "type": "gibt_es_nicht"}, id="unknown-type"),
        pytest.param({"id": "", "type": "clock"}, id="empty-id"),
        pytest.param({"type": "clock"}, id="no-id"),
        pytest.param({"id": "x"}, id="no-type"),
        pytest.param({"id": "x", "type": "clock", "area": 3}, id="area-too-high"),
        pytest.param({"id": "x", "type": "clock", "area": -1}, id="area-negative"),
        pytest.param({"id": "x", "type": "clock", "order": -1}, id="negative-order"),
    ],
)
def test_invalid_elements_are_refused(element):
    with pytest.raises(ValidationError):
        DisplayServiceConfig(elements=[element])


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"font_size": "huge"}, id="unknown-font-size"),
        pytest.param({"font": "comic-sans"}, id="unknown-font"),
        pytest.param({"i2c_bus": 0}, id="bus-zero"),
        pytest.param({"i2c_bus": -1}, id="bus-negative"),
        pytest.param({"i2c_address": -1}, id="address-negative"),
    ],
)
def test_invalid_top_level_values_are_refused(overrides):
    with pytest.raises(ValidationError):
        DisplayServiceConfig(**overrides)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def test_env_config_defaults_the_api_port():
    env = EnvConfig(
        mqtt_broker="mqtt",
        mqtt_port=1883,
        minabox_device_id="box1",
        log_level="INFO",
    )
    assert env.api_port == 8000


@pytest.mark.parametrize("port", [1023, 65536, 0, -1])
def test_env_config_refuses_an_unusable_api_port(port):
    with pytest.raises(ValidationError):
        EnvConfig(
            mqtt_broker="mqtt",
            mqtt_port=1883,
            minabox_device_id="box1",
            log_level="INFO",
            api_port=port,
        )


def test_app_config_no_longer_carries_a_second_display_config():
    """It was parsed at startup, never read, and went stale on the first reload."""
    from display_service.config_schema import AppConfig

    assert "display" not in AppConfig.model_fields


def test_the_config_path_points_where_the_container_mounts_it():
    assert DISPLAY_CONFIG_PATH.name == "display.json"
    assert DISPLAY_CONFIG_PATH.parent.name == "config"
    assert isinstance(DISPLAY_CONFIG_PATH, Path)
