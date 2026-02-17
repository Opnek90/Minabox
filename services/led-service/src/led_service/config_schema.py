from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt

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

class LEDServiceConfig(BaseModel):
    """Top-level LED configuration loaded from config/leds.json."""

    leds: List[LEDConfig] = Field(
        default_factory=list,
        description="Configured LEDs for this device.",
    )

class EnvConfig(BaseModel):
    """Environment-based configuration shared across Minabox services."""

    mqtt_broker: str = Field(
        min_length=1,
        description="Hostname of the MQTT broker (e.g. 'mqtt').",
    )
    mqtt_port: PositiveInt = Field(
        description="Port of the MQTT broker (e.g. 1883).",
    )
    minabox_device_id: str = Field(
        min_length=1,
        description="Device ID used in MQTT topics (e.g. 'box1').",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        description="Global log level for this service.",
    )

class AppConfig(BaseModel):
    """Combined configuration for the LED service.

    This is what the rest of the service should depend on.
    """

    env: EnvConfig
    leds: LEDServiceConfig
