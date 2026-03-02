"""Configuration schema for the display service."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt

from shared_lib.config import EnvConfigBase

DisplayElementType = Literal["volume", "sleep_timer", "mute", "play_state", "clock", "error_state", "repeat", "shuffle", "bluetooth"]
DisplayArea = Literal[0, 1, 2]  # 0=header (full width), 1=left column, 2=right column
DisplayFontSize = Literal["small", "medium", "large"]
DisplayFont = Literal["default", "sans", "mono"]


class DisplayElement(BaseModel):
    """Configuration for a single display element (widget)."""

    id: str = Field(min_length=1, description="Unique identifier (e.g. 'vol', 'time').")
    type: DisplayElementType = Field(
        description="Element type: volume, sleep_timer, mute, play_state, clock, error_state, repeat, shuffle, bluetooth.",
    )
    enabled: bool = Field(default=True, description="Whether this element is shown.")
    order: NonNegativeInt = Field(
        default=0,
        description="Display order within the area (lower = higher on screen).",
    )
    area: DisplayArea = Field(
        default=0,
        description="Area: 0=header (full width), 1=left column, 2=right column.",
    )


class DisplayServiceConfig(BaseModel):
    """Top-level display configuration loaded from config/display.json."""

    enabled: bool = Field(default=True, description="Display global on/off.")
    i2c_bus: PositiveInt = Field(default=1, description="I2C bus number (e.g. 1 for /dev/i2c-1).")
    i2c_address: NonNegativeInt = Field(
        default=60,
        description="I2C device address (60 = 0x3C for SSD1306).",
    )
    elements: List[DisplayElement] = Field(
        default_factory=list,
        description="List of display elements (order = screen order).",
    )
    font_size: DisplayFontSize = Field(
        default="medium",
        description="Text size: small (8px), medium (10px), large (12px).",
    )
    font: DisplayFont = Field(
        default="default",
        description="Font: default (built-in), sans, mono.",
    )


class EnvConfig(EnvConfigBase):
    """Environment-based configuration for the display service (extends shared base)."""


class AppConfig(BaseModel):
    """Combined configuration for the display service."""

    env: EnvConfig
    display: DisplayServiceConfig
