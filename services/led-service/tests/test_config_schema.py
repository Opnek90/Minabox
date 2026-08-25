"""Tests for the LED pattern schema.

The schema repairs rather than rejects. A config that fails validation stops
the service from starting at all, which is a far worse outcome than one binding
running with a default -- so every case here asserts a usable pattern, not a
ValidationError.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import structlog
from pydantic import ValidationError

from led_service.config_schema import (
    DEFAULT_BLINK_INTERVAL_MS,
    DEFAULT_GLOW_CYCLE_MS,
    DEFAULT_GLOW_MAX_BRIGHTNESS,
    DEFAULT_GLOW_MIN_BRIGHTNESS,
    DEFAULT_PULSE_DURATION_MS,
    EnvConfig,
    LEDPattern,
    LEDServiceConfig,
)

EXAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "config" / "leds.json.example"


@pytest.mark.parametrize("duration", [0, 500])
def test_solid_never_keeps_a_duration(duration: int) -> None:
    """A solid pattern means 'stay on'; a duration once left the LED dark (#97)."""
    pattern = LEDPattern(pattern_type="solid", duration_ms=duration)

    assert pattern.duration_ms is None


def test_off_drops_its_duration_too() -> None:
    pattern = LEDPattern(pattern_type="off", duration_ms=500)

    assert pattern.duration_ms is None


def test_blink_without_an_interval_falls_back_instead_of_failing() -> None:
    pattern = LEDPattern(pattern_type="blink")

    assert pattern.interval_ms == DEFAULT_BLINK_INTERVAL_MS


def test_blink_keeps_its_interval_and_drops_the_unused_duration() -> None:
    """Every shipped blink binding carries a duration_ms that does nothing."""
    pattern = LEDPattern(pattern_type="blink", interval_ms=200, duration_ms=500)

    assert pattern.interval_ms == 200
    assert pattern.duration_ms is None


@pytest.mark.parametrize("duration", [None, 0])
def test_pulse_without_a_usable_duration_falls_back(duration: int | None) -> None:
    """duration_ms 0 reached the coroutine, raised in its task, and killed the LED."""
    pattern = LEDPattern(pattern_type="pulse", duration_ms=duration)

    assert pattern.duration_ms == DEFAULT_PULSE_DURATION_MS


def test_pulse_keeps_a_real_duration() -> None:
    pattern = LEDPattern(pattern_type="pulse", duration_ms=250)

    assert pattern.duration_ms == 250


def test_glow_fills_in_its_defaults() -> None:
    pattern = LEDPattern(pattern_type="glow")

    assert pattern.cycle_ms == DEFAULT_GLOW_CYCLE_MS
    assert pattern.min_brightness == DEFAULT_GLOW_MIN_BRIGHTNESS
    assert pattern.max_brightness == DEFAULT_GLOW_MAX_BRIGHTNESS


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [(1.0, 1.0), (0.5, 0.5), (0.8, 0.2)],
)
def test_glow_repairs_a_range_it_cannot_breathe_in(
    minimum: float, maximum: float
) -> None:
    """min >= max raised inside the task, so the LED stayed dark and silent."""
    pattern = LEDPattern(
        pattern_type="glow", min_brightness=minimum, max_brightness=maximum
    )

    assert pattern.min_brightness == DEFAULT_GLOW_MIN_BRIGHTNESS
    assert pattern.max_brightness == DEFAULT_GLOW_MAX_BRIGHTNESS


def test_glow_keeps_a_valid_narrow_range() -> None:
    pattern = LEDPattern(
        pattern_type="glow", min_brightness=0.2, max_brightness=0.8, cycle_ms=1500
    )

    assert (pattern.min_brightness, pattern.max_brightness) == (0.2, 0.8)
    assert pattern.cycle_ms == 1500


def test_an_unknown_pattern_type_is_still_rejected() -> None:
    """Repairing is for values, not for a pattern the service cannot run."""
    with pytest.raises(ValidationError):
        LEDPattern(pattern_type="rainbow")


def test_the_shipped_example_config_validates() -> None:
    """The template every fresh install is seeded from must load as-is."""
    config = LEDServiceConfig.model_validate(
        json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    )

    assert [led.id for led in config.leds] == [
        "led_1",
        "led_2",
        "led_3",
        "led_4",
        "led_5",
    ]


# --- collisions the service cannot resolve on its own ------------------------


def test_two_leds_on_the_same_pin_are_reported() -> None:
    """The second one cannot claim the pin and ends up inert."""
    with structlog.testing.capture_logs() as logs:
        LEDServiceConfig.model_validate(
            {
                "leds": [
                    {"id": "led_1", "name": "A", "gpio": 17},
                    {"id": "led_2", "name": "B", "gpio": 17},
                ]
            }
        )

    warnings = [e for e in logs if e["event"] == "duplicate_led_gpio"]
    assert warnings and warnings[0]["gpio"] == [17]


def test_a_disabled_led_does_not_count_as_a_pin_collision() -> None:
    """It claims no pin, so sharing a number with an active LED is fine."""
    with structlog.testing.capture_logs() as logs:
        LEDServiceConfig.model_validate(
            {
                "leds": [
                    {"id": "led_1", "name": "A", "gpio": 17},
                    {"id": "led_2", "name": "B", "gpio": 17, "enabled": False},
                ]
            }
        )

    assert not [e for e in logs if e["event"] == "duplicate_led_gpio"]


def test_two_leds_with_the_same_id_are_reported() -> None:
    """The second overwrites the first in the controller map."""
    with structlog.testing.capture_logs() as logs:
        LEDServiceConfig.model_validate(
            {
                "leds": [
                    {"id": "led_1", "name": "A", "gpio": 17},
                    {"id": "led_1", "name": "B", "gpio": 27},
                ]
            }
        )

    warnings = [e for e in logs if e["event"] == "duplicate_led_id"]
    assert warnings and warnings[0]["led_id"] == ["led_1"]


def test_a_pin_outside_the_bcm_range_is_reported() -> None:
    with structlog.testing.capture_logs() as logs:
        LEDServiceConfig.model_validate(
            {"leds": [{"id": "led_1", "name": "A", "gpio": 999}]}
        )

    assert any(e["event"] == "led_gpio_outside_bcm_range" for e in logs)


def test_a_clean_config_warns_about_nothing() -> None:
    with structlog.testing.capture_logs() as logs:
        LEDServiceConfig.model_validate(
            {
                "leds": [
                    {"id": "led_1", "name": "A", "gpio": 17},
                    {"id": "led_2", "name": "B", "gpio": 27},
                ]
            }
        )

    assert logs == []


# --- environment -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("false", False), ("True", True), (None, False)],
)
def test_disable_gpio_comes_from_the_environment(
    raw: str | None, expected: bool
) -> None:
    """It used to be read straight from os.getenv in two separate places."""
    fields = {
        "mqtt_broker": "mqtt",
        "mqtt_port": 1883,
        "minabox_device_id": "box",
        "log_level": "INFO",
    }
    if raw is not None:
        fields["disable_gpio"] = raw

    assert EnvConfig(**fields).disable_gpio is expected
