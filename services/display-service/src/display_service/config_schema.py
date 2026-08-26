"""Configuration schema for the display service.

What used to be here was a layout: nine element types, three areas, an order
and a font. That grid is gone - every state of the box has a screen of its own
now, and each screen picks its own sizes - so the file it was configured from
is down to the hardware and an on/off switch.

Pydantic ignores unknown keys, so an existing display.json still loads with its
``elements`` list in it. Nothing reads it.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt, field_validator
from shared_lib.config import EnvConfigBase

_CLOCK_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class BrightnessConfig(BaseModel):
    """How bright the panel is, and when it gives up for the night.

    This device stands in a child's bedroom. At full contrast at eight in the
    evening it is a light source, and the cost of doing something about it is
    two bytes on the bus - `contrast()` is a single command.

    Dimming alone is not enough for a dark room: luma says so itself, that a
    low level "will not necessarily dim the display to nearly off". That is
    what ``off_at_night`` is for - the panel is switched off outright, and only
    while there is nothing to say. Anything actually happening (something
    playing, a hand on the knob, a figure on the reader) takes it back.
    """

    day: int = Field(default=255, ge=0, le=255, description="Contrast by day.")
    night: int = Field(default=40, ge=0, le=255, description="Contrast at night.")
    night_from: str = Field(default="20:00", description="Start of night, HH:MM.")
    night_to: str = Field(default="07:00", description="End of night, HH:MM.")
    off_at_night: bool = Field(
        default=False,
        description="Switch the panel off at night while nothing is happening.",
    )

    @field_validator("night_from", "night_to")
    @classmethod
    def _a_clock_time(cls, value: str) -> str:
        if not _CLOCK_TIME.match(value):
            raise ValueError("must be a time of day as HH:MM, e.g. 20:00")
        return value


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
    brightness: BrightnessConfig = Field(
        default_factory=BrightnessConfig,
        description="Panel brightness, and the night window.",
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
