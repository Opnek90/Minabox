"""What the display still reads from its config file.

The layout used to live here: nine element types, three areas, an order, a
font. That grid is gone - every state of the box has a screen of its own now,
and each screen picks its own sizes - so what is left is the hardware and an
on/off switch.

The part worth pinning down is what happens to a file that still has the old
keys in it. Pydantic ignores them, which is what lets the config on a running
box stay as it is instead of needing a migration.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from display_service.config_schema import DisplayServiceConfig


def test_an_empty_file_is_a_working_config():
    cfg = DisplayServiceConfig()
    assert cfg.enabled is True
    assert cfg.i2c_bus == 1
    assert cfg.i2c_address == 60


def test_the_hardware_can_be_set():
    cfg = DisplayServiceConfig(enabled=False, i2c_bus=3, i2c_address=61)
    assert (cfg.enabled, cfg.i2c_bus, cfg.i2c_address) == (False, 3, 61)


def test_the_old_layout_keys_are_ignored_rather_than_rejected():
    """A box running today has them in its file, and it must keep starting."""
    cfg = DisplayServiceConfig(
        enabled=True,
        i2c_bus=1,
        i2c_address=60,
        font="terminus",
        font_size="large",
        elements=[
            {"id": "vol", "type": "volume", "area": 1, "order": 0, "enabled": True},
            {"id": "time", "type": "clock", "area": 0, "order": 0, "enabled": True},
        ],
    )
    assert cfg.enabled is True
    assert not hasattr(cfg, "elements")


def test_nonsense_in_the_old_keys_is_ignored_too():
    """They are not read, so they cannot be wrong."""
    cfg = DisplayServiceConfig(elements="not even a list", font=42)
    assert cfg.i2c_address == 60


@pytest.mark.parametrize(
    "field,value",
    [("i2c_bus", 0), ("i2c_bus", -1), ("i2c_address", -1), ("enabled", "vielleicht")],
)
def test_the_hardware_fields_are_still_checked(field, value):
    with pytest.raises(ValidationError):
        DisplayServiceConfig(**{field: value})
