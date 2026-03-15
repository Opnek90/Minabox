from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt

from shared_lib.config import EnvConfigBase

PatternType = Literal["solid", "blink", "pulse", "off"]

class LEDPattern(BaseModel):
    """Pattern description for a logical state on a single LED.

    Matches the pattern objects used in config/leds.json as documented in the
    LED service architecture.
    """

    pattern_type: PatternType = Field(
        description=(
            "Type of LED pattern: 'solid', 'blink', 'pulse' or 'off'. "
            "'off' simply turns the LED off immediately without any visible pulse."
        ),
    )
    duration_ms: NonNegativeInt | None = Field(
        default=None,
        description=(
            "Pattern duration in milliseconds. "
            "For 'solid', 0 or None means active until overridden. "
            "For 'pulse', how long the LED stays on per pulse."
        ),
    )
    interval_ms: PositiveInt | None = Field(
        default=None,
        description="Blink interval in milliseconds; required for 'blink' patterns.",
    )
    repeat: NonNegativeInt | None = Field(
        default=None,
        description=(
            "Number of repetitions. 0 or None means repeat indefinitely "
            "until another pattern overrides this one."
        ),
    )

class LEDConfig(BaseModel):
    """Configuration for a single physical LED."""

    id: str = Field(
        min_length=1,
        description="Internal LED identifier (e.g. 'led_5').",
    )
    name: str = Field(
        min_length=1,
        description="Human-readable name for UI and logs (e.g. 'Power-LED').",
    )
    gpio: PositiveInt = Field(
        description="GPIO pin number the LED is connected to.",
    )
    bindings: Dict[str, LEDPattern] = Field(
        default_factory=dict,
        description=(
            "Mapping from logical state (e.g. 'system_online', 'audio_playing') "
            "to a concrete LED pattern."
        ),
    )
    enabled: bool = Field(
        default=True,
        description=(
            "When False the LED ignores all state changes and stays off. "
            "Defaults to True so existing configs are unaffected."
        ),
    )

class LEDServiceConfig(BaseModel):
    """Top-level LED configuration loaded from config/leds.json."""

    leds: List[LEDConfig] = Field(
        default_factory=list,
        description="Configured LEDs for this device.",
    )

class EnvConfig(EnvConfigBase):
    """Environment-based configuration for the LED service (extends shared base)."""


class AppConfig(BaseModel):
    """Combined configuration for the LED service.

    This is what the rest of the service should depend on.
    """

    env: EnvConfig
    leds: LEDServiceConfig
