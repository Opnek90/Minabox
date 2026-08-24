from __future__ import annotations

from typing import Literal

import structlog
from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt, model_validator
from shared_lib.config import EnvConfigBase

logger = structlog.get_logger(__name__)

PatternType = Literal["solid", "blink", "pulse", "off", "glow"]

# Fallbacks for pattern fields the WebUI can leave empty or set to a value that
# would make the pattern impossible to run. The schema repairs those instead of
# rejecting them: a config that fails validation takes the whole service down
# on the next start, and one unusable binding is not worth that.
DEFAULT_BLINK_INTERVAL_MS = 500
DEFAULT_PULSE_DURATION_MS = 250
DEFAULT_GLOW_CYCLE_MS = 2000
DEFAULT_GLOW_MIN_BRIGHTNESS = 0.0
DEFAULT_GLOW_MAX_BRIGHTNESS = 1.0


class LEDPattern(BaseModel):
    """Pattern description for a logical state on a single LED.

    Matches the pattern objects used in config/leds.json as documented in the
    LED service architecture.
    """

    pattern_type: PatternType = Field(
        description=(
            "Type of LED pattern: 'solid', 'blink', 'pulse', 'off' or 'glow'. "
            "'off' simply turns the LED off immediately without any visible pulse. "
            "'glow' creates a smooth breathing/fading effect via Software PWM (PWMLED)."
        ),
    )
    duration_ms: NonNegativeInt | None = Field(
        default=None,
        description=(
            "On-time per pulse in milliseconds. Only used by 'pulse'; cleared "
            "for every other pattern type."
        ),
    )
    interval_ms: PositiveInt | None = Field(
        default=None,
        description="Blink interval in milliseconds; required for 'blink' patterns.",
    )
    repeat: NonNegativeInt | None = Field(
        default=None,
        description=(
            "Number of complete cycles -- one blink is on and off again, one "
            "pulse is on and off again, one glow cycle is dark to bright and "
            "back. 0 or None means repeat indefinitely until another pattern "
            "overrides this one."
        ),
    )
    cycle_ms: int | None = Field(
        default=None,
        ge=500,
        description=(
            "Duration of one full glow cycle (dark -> bright -> dark) in milliseconds. "
            "Only used for 'glow'. Default: 2000. Minimum: 500."
        ),
    )
    min_brightness: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum brightness for 'glow' pattern (0.0 = fully off). "
            "Only used for 'glow'. Default: 0.0."
        ),
    )
    max_brightness: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Maximum brightness for 'glow' pattern (1.0 = fully on). "
            "Only used for 'glow'. Default: 1.0."
        ),
    )

    @model_validator(mode="after")
    def normalise_for_pattern_type(self) -> LEDPattern:
        """Fill in what a pattern needs and drop what it cannot use.

        Every value here used to be trusted as written. A 'pulse' with
        duration_ms 0 or a 'glow' whose min_brightness was not below its
        max_brightness reached the pattern coroutine, raised inside its task,
        and left the LED dark without a single log line.

        Repairing is deliberate: the WebUI can produce all of these, and a
        binding that lights up with a default is a better answer than a service
        that refuses to start.
        """
        if self.pattern_type == "solid":
            self._clear_duration_for_solid()
        elif self.pattern_type == "off":
            self.duration_ms = None
        elif self.pattern_type == "blink":
            self._require_blink_interval()
            # Blink has never used duration_ms; keeping it only invites the
            # assumption that it shortens the pattern.
            self.duration_ms = None
        elif self.pattern_type == "pulse":
            self._require_pulse_duration()
        elif self.pattern_type == "glow":
            self._resolve_glow_range()
            self.duration_ms = None
        return self

    def _clear_duration_for_solid(self) -> None:
        """A solid pattern stays on; a duration would contradict that (bug #97)."""
        if self.duration_ms:
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

    def _require_blink_interval(self) -> None:
        if self.interval_ms is None:
            logger.warning(
                "blink_interval_defaulted",
                default_ms=DEFAULT_BLINK_INTERVAL_MS,
                detail=(
                    "A 'blink' binding without interval_ms cannot blink. Falling "
                    "back to the default interval; set one in the UI."
                ),
            )
            self.interval_ms = DEFAULT_BLINK_INTERVAL_MS

    def _require_pulse_duration(self) -> None:
        if not self.duration_ms:
            logger.warning(
                "pulse_duration_defaulted",
                duration_ms=self.duration_ms,
                default_ms=DEFAULT_PULSE_DURATION_MS,
                detail=(
                    "A 'pulse' binding needs a duration_ms above zero. Falling "
                    "back to the default; set one in the UI."
                ),
            )
            self.duration_ms = DEFAULT_PULSE_DURATION_MS

    def _resolve_glow_range(self) -> None:
        if self.cycle_ms is None:
            self.cycle_ms = DEFAULT_GLOW_CYCLE_MS
        if self.min_brightness is None:
            self.min_brightness = DEFAULT_GLOW_MIN_BRIGHTNESS
        if self.max_brightness is None:
            self.max_brightness = DEFAULT_GLOW_MAX_BRIGHTNESS

        if self.min_brightness >= self.max_brightness:
            logger.warning(
                "glow_brightness_range_invalid",
                min_brightness=self.min_brightness,
                max_brightness=self.max_brightness,
                detail=(
                    "min_brightness must stay below max_brightness or the LED "
                    "cannot breathe. Falling back to the full range."
                ),
            )
            self.min_brightness = DEFAULT_GLOW_MIN_BRIGHTNESS
            self.max_brightness = DEFAULT_GLOW_MAX_BRIGHTNESS


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
    bindings: dict[str, LEDPattern] = Field(
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

    leds: list[LEDConfig] = Field(
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
