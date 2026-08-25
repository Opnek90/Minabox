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
from led_service.core import led_controller, led_patterns
from led_service.core.led_controller import LEDController, LEDManager

pytestmark = pytest.mark.asyncio

SOLID = LEDPattern(pattern_type="solid")
BLINK = LEDPattern(pattern_type="blink", interval_ms=100, repeat=1)
OFF = LEDPattern(pattern_type="off")


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(led_patterns, "_sleep_or_cancel", fake)
    return fake


def controller_for(config, led: FakeLED | None = None) -> LEDController:
    controller = LEDController(config, disable_gpio=True)
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
    controller = LEDController(make_led(audio_playing=SOLID), disable_gpio=True)

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
    await _settle()

    assert sum(clock.waits) == pytest.approx(5.0)


async def test_the_test_blink_returns_before_it_has_finished() -> None:
    """The backend proxies POST /test with a five second timeout.

    Awaiting a five second blink here would race that timeout, so the call has
    to come back as soon as the blink is running.
    """
    controller = controller_for(make_led())

    started = await asyncio.wait_for(
        controller.run_test_blink(duration_sec=5.0), timeout=0.5
    )

    assert started is True
    assert controller._current_task is not None
    await controller.cleanup()


async def test_the_test_blink_ignores_the_bindings(clock: FakeClock) -> None:
    led = FakeLED()
    controller = controller_for(make_led(), led)

    await controller.run_test_blink(duration_sec=2.0)
    await _settle()

    assert led.transitions.count("on") == 2


async def test_a_real_state_change_preempts_the_test_blink(
    clock: FakeClock,
) -> None:
    """A card scanned during a test must win over the test."""
    led = FakeLED()
    controller = controller_for(make_led(audio_playing=SOLID), led)

    await controller.run_test_blink(duration_sec=5.0)
    await apply(controller, "audio_playing")

    assert controller._current_logical_state == "audio_playing"
    assert led.transitions[-1] == "on"


async def test_the_test_blink_reports_missing_hardware() -> None:
    controller = LEDController(make_led(), disable_gpio=True)

    assert await controller.run_test_blink(duration_sec=1.0) is False


async def _settle() -> None:
    """Give the pattern task and its done-callback a turn on the loop."""
    for _ in range(3):
        await asyncio.sleep(0)


# --- what a controller does before it ever runs a pattern --------------------


async def test_a_disabled_led_never_claims_its_pin() -> None:
    """Switching an LED off in the UI has to free the GPIO for something else."""
    with structlog.testing.capture_logs() as logs:
        controller = LEDController(
            make_led(enabled=False, audio_playing=SOLID), disable_gpio=True
        )

    assert controller._led is None
    assert controller.is_available is False
    assert [entry["event"] for entry in logs] == ["led_disabled_pin_not_claimed"]


async def test_the_pin_factory_is_created_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gpiozero never closes the factory it replaces.

    Re-assigning it on every config reload leaked an open /dev/gpiochip0
    handle per save in the WebUI.
    """
    from gpiozero import Device

    created = []
    monkeypatch.setattr(Device, "pin_factory", Device.pin_factory, raising=False)
    monkeypatch.setattr(led_controller, "_pin_factory_ready", False)
    monkeypatch.setattr(
        led_controller, "_make_pin_factory", lambda: created.append(1) or object()
    )

    led_controller._ensure_pin_factory()
    led_controller._ensure_pin_factory()
    led_controller._ensure_pin_factory()

    assert len(created) == 1


async def test_dev_mode_never_touches_the_pin_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(led_controller, "_ensure_pin_factory", lambda: calls.append(1))
    manager = LEDManager(disable_gpio=True)

    await manager.initialize_leds([make_led()])

    assert calls == []


async def test_the_manager_counts_configured_and_available_separately() -> None:
    """/health has to tell 'five LEDs' apart from 'five LEDs that work'."""
    manager = LEDManager(disable_gpio=True)

    await manager.initialize_leds([make_led("led_1"), make_led("led_2", gpio=27)])

    assert manager.led_count == 2
    assert manager.available_count == 0


async def test_leds_that_all_fail_to_claim_a_pin_are_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wrong GPIO group id after an update kills every LED at once.

    The controller is stubbed rather than pointed at a bad pin number: this
    suite must never reach real GPIO, not even to watch it fail.
    """

    class UnavailableController:
        def __init__(self, config, *, disable_gpio: bool = False) -> None:
            self.config = config
            self.is_available = False

        def close_sync(self) -> None:
            pass

    monkeypatch.setattr(led_controller, "_ensure_pin_factory", lambda: None)
    monkeypatch.setattr(led_controller, "LEDController", UnavailableController)
    manager = LEDManager()

    with structlog.testing.capture_logs() as logs:
        await manager.initialize_leds([make_led("led_1")])

    assert any(entry["event"] == "no_leds_available" for entry in logs)


async def test_working_leds_are_not_reported_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class WorkingController:
        def __init__(self, config, *, disable_gpio: bool = False) -> None:
            self.config = config
            self.is_available = True

        def close_sync(self) -> None:
            pass

    monkeypatch.setattr(led_controller, "_ensure_pin_factory", lambda: None)
    monkeypatch.setattr(led_controller, "LEDController", WorkingController)
    manager = LEDManager()

    with structlog.testing.capture_logs() as logs:
        await manager.initialize_leds([make_led("led_1")])

    assert not any(entry["event"] == "no_leds_available" for entry in logs)
    assert manager.available_count == 1


# --- releasing the pin while a pattern is running ----------------------------

GLOW = LEDPattern(pattern_type="glow", cycle_ms=2000, repeat=0)


async def test_closing_does_not_write_to_a_released_pin() -> None:
    """task.cancel() only requests cancellation; close() has to await it.

    Releasing the pin first left the still-suspended pattern to run its finally
    block against a closed device. Every config save in the WebUI logged a
    GPIODeviceClosed for the glowing ring that way.
    """
    led = FakeLED()
    controller = controller_for(make_led(rfid_removed=GLOW), led)
    controller._is_pwm = True

    with structlog.testing.capture_logs() as logs:
        await apply(controller, "rfid_removed")
        await controller.close()
        await _settle()

    assert not [e for e in logs if e["event"] == "pattern_task_failed"]
    assert led.closed is True
    assert led.values[-1] == 0.0


async def test_reinitialising_stops_a_running_pattern_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same path as a config save: initialize_leds() over a live glow."""
    monkeypatch.setattr(led_controller, "_ensure_pin_factory", lambda: None)
    manager = LEDManager(disable_gpio=True)
    config = make_led(rfid_removed=GLOW)
    await manager.initialize_leds([config])

    led = FakeLED()
    controller = manager._controllers[config.id]
    controller._led = led
    controller._gpio_available = True
    controller._is_pwm = True
    await apply(controller, "rfid_removed")

    with structlog.testing.capture_logs() as logs:
        await manager.initialize_leds([config])
        await _settle()

    assert not [e for e in logs if e["event"] == "pattern_task_failed"]
    assert led.closed is True


async def test_closing_twice_is_harmless() -> None:
    led = FakeLED()
    controller = controller_for(make_led(audio_playing=SOLID), led)

    await apply(controller, "audio_playing")
    await controller.close()
    await controller.close()
    await controller.cleanup()

    assert led.closed is True
