"""Configuration schema for the display service.

What used to be here was a layout: nine element types, three areas, an order
and a font. That grid is gone - every state of the box has a screen of its own
now, and each screen picks its own sizes - so the file it was configured from
is down to the hardware and an on/off switch.

Pydantic ignores unknown keys, so an existing display.json still loads with its
``elements`` list in it. Nothing reads it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt
from shared_lib.config import EnvConfigBase


class DisplayServiceConfig(BaseModel):
    """Top-level display configuration loaded from config/display.json."""

    enabled: bool = Field(default=True, description="Display global on/off.")
    i2c_bus: PositiveInt = Field(
        default=1,
        description="I2C bus number (e.g. 1 for /dev/i2c-1).",
    )
    i2c_address: NonNegativeInt = Field(
        default=60,
        description="I2C device address (60 = 0x3C for SSD1306).",
    )


class EnvConfig(EnvConfigBase):
    """Environment-based configuration for the display service (extends shared base)."""

    api_port: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="REST API port for the display service (issue #39).",
    )


class AppConfig(BaseModel):
    """Environment configuration for the display service.

    The display config itself is owned by ConfigManager, which can reload it;
    keeping a second copy here meant keeping a stale one.
    """

    env: EnvConfig
