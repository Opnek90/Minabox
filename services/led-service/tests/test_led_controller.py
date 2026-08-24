"""Tests for LEDController: when a pattern starts, and what happens if it fails.

The controller is built around a GPIO object it creates itself, so the tests
set DISABLE_GPIO and then inject a FakeLED. Reaching into the two private
attributes is deliberate -- the alternative is a gpiozero mock that tests
gpiozero rather than this class.
"""

from __future__ import annotations

import asyncio

import pytest
import structlog
from led_test_doubles import FakeClock, FakeLED, make_led

from led_service.config_schema import LEDPattern
from led_service.core import led_patterns
from led_service.core.led_controller import LEDController

pytestmark = pytest.mark.asyncio

SOLID = LEDPattern(pattern_type="solid")
BLINK = LEDPattern(pattern_type="blink", interval_ms=100, repeat=1)
OFF = LEDPattern(pattern_type="off")


@pytest.fixture(autouse=True)
def no_gpio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISABLE_GPIO", "true")


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(led_patterns, "_sleep_or_cancel", fake)
    return fake


def controller_for(config, led: FakeLED | None = None) -> LEDController:
    controller = LEDController(config)
    controller._led = led or FakeLED()
    controller._gpio_available = True
    return controller


async def apply(controller: LEDController, logical_state: str) -> None:
    """Apply a state and let its task run, as the event loop would in service."""
    await controller.apply_pattern(logical_state)
    await _settle()


# --- when a pattern is skipped ----------------------------------------------


async def test_a_repeated_solid_state_is_applied_only_once() -> None:
    """A solid task finishes at once, which used to defeat the whole check.

    audio/status repeats while a track plays, so every message restarted the
    pattern and logged an INFO line about once a second.
    """
    led = FakeLED()
    controller = controller_for(make_led(audio_playing=SOLID), led)

    await apply(controller, "audio_playing")
    await apply(controller, "audio_playing")
    await apply(controller, "audio_playing")

    assert led.transitions == ["on"]


async def test_a_repeated_off_state_is_applied_only_once() -> None:
    led = FakeLED()
    controller = controller_for(make_led(audio_stopped=OFF), led)

    await apply(controller, "audio_stopped")
    await apply(controller, "audio_stopped")

    assert led.transitions == ["off"]


async def test_a_different_state_in_between_starts_the_pattern_again() -> None:
    led = FakeLED()
    controller = controller_for(make_led(audio_playing=SOLID, audio_stopped=OFF), led)

    await apply(controller, "audio_playing")
    await apply(controller, "audio_stopped")
    await apply(controller, "audio_playing")

    assert led.transitions == ["on", "off", "on"]


async def test_a_finished_blink_may_run_again(clock: FakeClock) -> None:
    """Only persistent patterns are idempotent; a blink is an event, not a state."""
    led = FakeLED()
    controller = controller_for(make_led(button_pressed=BLINK), led)

    await apply(controller, "button_pressed")
    await apply(controller, "button_pressed")

    assert led.transitions.count("on") == 2


async def test_a_disabled_led_ignores_every_state() -> None:
    led = FakeLED()
    controller = controller_for(make_led(enabled=False, audio_playing=SOLID), led)

    await apply(controller, "audio_playing")

    assert led.transitions == []


async def test_a_state_without_a_binding_leaves_the_led_alone() -> None:
    led = FakeLED()
    controller = controller_for(make_led(audio_playing=SOLID), led)

    await apply(controller, "system_error")

    assert led.transitions == []


async def test_an_led_without_hardware_does_nothing() -> None:
    controller = LEDController(make_led(audio_playing=SOLID))

    await apply(controller, "audio_playing")

    assert controller._gpio_available is False


# --- when a pattern fails ----------------------------------------------------


async def test_a_failing_pattern_is_logged_instead_of_disappearing() -> None:
    """The done-callback swallowed the exception and asyncio stayed quiet too."""
    controller = controller_for(
        make_led(audio_playing=SOLID), FakeLED(fail_on_switch=True)
    )

    with structlog.testing.capture_logs() as logs:
        await apply(controller, "audio_playing")

    failures = [entry for entry in logs if entry["event"] == "pattern_task_failed"]
    assert len(failures) == 1
    assert failures[0]["log_level"] == "error"


async def test_a_failed_pattern_does_not_block_the_next_attempt() -> None:
    """A persistent state that failed must not look like it is still showing."""
    controller = controller_for(
        make_led(audio_playing=SOLID), FakeLED(fail_on_switch=True)
    )

    await apply(controller, "audio_playing")

    assert controller._current_logical_state is None


# --- the test blink ----------------------------------------------------------


async def test_the_test_blink_lasts_the_requested_five_seconds(
    clock: FakeClock,
) -> None:
    """It asked for 5 toggles at 500 ms and therefore ran for 2.5 seconds."""
    controller = controller_for(make_led())

    assert await controller.run_test_blink(duration_sec=5.0) is True
    assert sum(clock.waits) == pytest.approx(5.0)


async def test_the_test_blink_ignores_the_bindings(clock: FakeClock) -> None:
    led = FakeLED()
    controller = controller_for(make_led(), led)

    await controller.run_test_blink(duration_sec=2.0)

    assert led.transitions.count("on") == 2


async def test_the_test_blink_reports_missing_hardware() -> None:
    controller = LEDController(make_led())

    assert await controller.run_test_blink(duration_sec=1.0) is False


async def _settle() -> None:
    """Give the pattern task and its done-callback a turn on the loop."""
    for _ in range(3):
        await asyncio.sleep(0)
