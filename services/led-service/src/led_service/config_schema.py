from __future__ import annotations

import structlog
from typing import Dict, List, Literal

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt, model_validator

from shared_lib.config import EnvConfigBase

logger = structlog.get_logger(__name__)

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
            "Not applicable for 'solid' (ignored with a warning). "
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

    @model_validator(mode="after")
    def clear_duration_for_solid(self) -> "LEDPattern":
        """Ensure duration_ms is always None for solid patterns.

        The solid pattern means 'stay on indefinitely'. A non-zero duration_ms
        has no meaning here and previously caused the LED not to light up at all
        (bug #97). We strip it at parse time and emit a warning so the config
        can be corrected in the UI.
        """
        if self.pattern_type == "solid" and self.duration_ms is not None and self.duration_ms > 0:
            logger.warning(
                "solid_pattern_duration_ignored",
                duration_ms=self.duration_ms,
                detail=(
                    "duration_ms has no effect on the 'solid' pattern and has been "
                    "cleared. The LED will stay on indefinitely. Please remove "
                    "duration_ms from this binding in the UI to suppress this warning."
                ),
            )
            self.duration_ms = None
        return self

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
