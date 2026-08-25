"""LED controller for managing physical GPIO-based LEDs.

This module handles:
- Initialization of GPIO pins via gpiozero (LGPIOFactory for PWMLED support)
- Pattern execution and cancellation
- LED state management with graceful fallback for dev environments
- PWM support for the 'glow' pattern via PWMLED
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog

from ..config_schema import LEDConfig, LEDPattern
from ..exceptions import GPIOControlError, InvalidPatternError
from .led_patterns import (
    run_blink_pattern,
    run_glow_pattern,
    run_off_pattern,
    run_pulse_pattern,
    run_solid_pattern,
)

logger = structlog.get_logger(__name__)

# Pattern types that represent persistent states (LED stays as-is after task finishes).
# These must NOT clear _current_logical_state so subsequent identical events are
# correctly suppressed by the idempotency check in apply_pattern().
_PERSISTENT_PATTERN_TYPES = frozenset({"solid", "off", "glow"})

# What run_test_blink() drives, independent of any binding.
_TEST_BLINK_INTERVAL_MS = 500
_TEST_BLINK_STATE = "test_blink"

# Set once per process. gpiozero keeps the factory in a class attribute and
# never closes the one it replaces, so re-assigning it on every config reload
# leaked an open /dev/gpiochip0 handle per save.
_pin_factory_ready = False


def _led_needs_pwm(config: LEDConfig) -> bool:
    """Return True if any binding in this LED config requires PWM (PWMLED)."""
    return any(p.pattern_type == "glow" for p in config.bindings.values())


def _make_pin_factory() -> Any:
    """Create the lgpio-backed pin factory. Separated so tests can replace it."""
    from gpiozero.pins.lgpio import LGPIOFactory

    return LGPIOFactory()


def _ensure_pin_factory() -> None:
    """Point gpiozero at LGPIOFactory, once.

    LGPIOFactory (via lgpio) supports software PWM through /dev/gpiochip0
    inside Docker without a pigpiod daemon. NativeFactory does not support PWM
    and is deliberately not used (issue #36).
    """
    global _pin_factory_ready
    if _pin_factory_ready:
        return
    try:
        from gpiozero import Device

        Device.pin_factory = _make_pin_factory()
        _pin_factory_ready = True
        logger.debug("gpio_pin_factory_set", factory="LGPIOFactory")
    except Exception as exc:
        # Left unset so the next initialisation tries again.
        logger.warning("gpio_pin_factory_set_failed", error=str(exc))


class LEDController:
    """Controls a single physical LED and its pattern execution."""

    def __init__(self, config: LEDConfig, *, disable_gpio: bool = False) -> None:
        """Initialize LED controller.

        The pin factory is expected to be set by LEDManager before any
        controller is created (issue #36).

        If any binding uses the 'glow' pattern, PWMLED is instantiated
        instead of LED. PWMLED is backward-compatible: value=1.0 equals on(),
        value=0.0 equals off().

        A disabled LED claims no pin at all. It used to claim one and then
        ignore every state, which meant switching an LED off in the UI did not
        free its GPIO for anything else.

        Args:
            config: LED configuration including GPIO pin and bindings.
            disable_gpio: Skip all hardware access (development without a Pi).
        """
        self.config = config
        self._lock = asyncio.Lock()
        self._current_task: asyncio.Task[None] | None = None
        self._cancel_event = asyncio.Event()
        self._current_logical_state: str | None = None
        self._gpio_available = False
        self._led = None
        self._is_pwm = False

        if not config.enabled:
            logger.debug(
                "led_disabled_pin_not_claimed",
                led_id=config.id,
                led_name=config.name,
                gpio=config.gpio,
            )
            return

        if disable_gpio:
            logger.debug(
                "gpio_disabled_dev_mode",
                led_id=config.id,
                led_name=config.name,
                reason="DISABLE_GPIO environment variable",
            )
            return

        try:
            use_pwm = _led_needs_pwm(config)
            if use_pwm:
                from gpiozero import PWMLED

                self._led = PWMLED(config.gpio)
                self._is_pwm = True
            else:
                from gpiozero import LED

                self._led = LED(config.gpio)
            self._gpio_available = True
            logger.debug(
                "led_initialized",
                led_id=config.id,
                led_name=config.name,
                gpio=config.gpio,
                pwm=use_pwm,
            )
        except Exception as exc:
            logger.warning(
                "gpio_unavailable_fallback",
                led_id=config.id,
                led_name=config.name,
                gpio=config.gpio,
                error=str(exc),
                hint="Set DISABLE_GPIO=true for dev mode without hardware",
            )

    @property
    def is_available(self) -> bool:
        """True when this controller actually holds a usable GPIO pin."""
        return self._gpio_available

    async def close(self) -> None:
        """Stop the running pattern and release the GPIO pin (issue #37).

        Called by LEDManager.initialize_leds() before building new controllers,
        and by cleanup() at shutdown. Safe to call more than once.

        The cancellation is awaited before the device is released. This used to
        be a synchronous close_sync() that only *requested* cancellation:
        task.cancel() takes effect the next time the task is scheduled, so the
        pin was already gone by the time the pattern woke up, and the pattern's
        own finally block then wrote to a closed device. On every config save
        in the WebUI that produced a GPIODeviceClosed on the glowing ring.
        """
        async with self._lock:
            await self._cancel_current_pattern()
        self._release_led()

    def _release_led(self) -> None:
        """Switch the LED off and hand the pin back. Works for LED and PWMLED."""
        if self._led is None:
            return
        try:
            if self._is_pwm:
                self._led.value = 0.0
            else:
                self._led.off()
        except Exception:
            logger.warning("led_off_failed", led_id=self.config.id, exc_info=True)
        try:
            self._led.close()
        except Exception:
            logger.warning("led_close_failed", led_id=self.config.id, exc_info=True)
        self._led = None
        self._gpio_available = False
        self._is_pwm = False

    async def apply_pattern(self, logical_state: str) -> None:
        """Apply the pattern for a given logical state.

        Skips immediately when the LED is disabled (issue #62).

        Args:
            logical_state: The logical state to apply (e.g. 'audio_playing').
        """
        if not self.config.enabled:
            logger.debug(
                "pattern_skipped_disabled",
                led_id=self.config.id,
                logical_state=logical_state,
            )
            return

        if not self._gpio_available:
            logger.debug(
                "pattern_skipped_no_hardware",
                led_id=self.config.id,
                logical_state=logical_state,
            )
            return

        pattern = self.config.bindings.get(logical_state)
        if pattern is None:
            logger.debug(
                "no_pattern_binding",
                led_id=self.config.id,
                logical_state=logical_state,
            )
            return

        # Cancelling the old pattern and starting the new one has to happen as
        # one step. Two state changes arriving together -- rfid/presence and
        # rfid/tag-scanned do, three milliseconds apart -- could otherwise both
        # cancel, both start, and leave the first pattern running unowned.
        async with self._lock:
            if self._is_already_showing(logical_state, pattern):
                logger.debug(
                    "pattern_skipped_idempotent",
                    led_id=self.config.id,
                    logical_state=logical_state,
                )
                return

            await self._cancel_current_pattern()

            try:
                await self._start_pattern(logical_state, pattern)
            except Exception as exc:
                logger.error(
                    "pattern_execution_failed",
                    led_id=self.config.id,
                    logical_state=logical_state,
                    pattern_type=pattern.pattern_type,
                    error=str(exc),
                    exc_info=True,
                )
                raise GPIOControlError(
                    f"Pattern execution failed for LED '{self.config.name}': {exc}"
                ) from exc

    def _is_already_showing(self, logical_state: str, pattern: LEDPattern) -> bool:
        """True when re-applying this state would not change anything visible.

        A persistent pattern finishes its task the moment the LED is set, so
        asking whether that task is still running answered "no" for exactly the
        three pattern types the check was written for. Every repeated
        audio/status message therefore restarted a solid pattern and logged an
        INFO line, roughly once a second during playback.
        """
        if self._current_logical_state != logical_state:
            return False
        if pattern.pattern_type in _PERSISTENT_PATTERN_TYPES:
            return True
        return self._current_task is not None and not self._current_task.done()

    async def _start_pattern(self, logical_state: str, pattern: LEDPattern) -> None:
        """Start executing a pattern.

        Args:
            logical_state: The logical state this pattern represents.
            pattern: The pattern configuration to execute.
        """
        self._cancel_event.clear()
        self._current_logical_state = logical_state

        logger.info(
            "led_state_changed",
            led_id=self.config.id,
            led_name=self.config.name,
            logical_state=logical_state,
            pattern_type=pattern.pattern_type,
        )

        self._launch(self._build_pattern(pattern), logical_state, pattern.pattern_type)

    def _build_pattern(self, pattern: LEDPattern) -> Coroutine[Any, Any, None]:
        """Return the coroutine that renders this pattern.

        The ``is None`` guards are type narrowing. LEDPattern fills every field
        a pattern needs, so none of them should ever fire in practice.
        """
        if pattern.pattern_type == "solid":
            return run_solid_pattern(self._led, self.config.id)

        if pattern.pattern_type == "off":
            return run_off_pattern(self._led, self.config.id)

        if pattern.pattern_type == "blink":
            if pattern.interval_ms is None:
                raise InvalidPatternError(
                    f"Blink pattern for LED '{self.config.name}' missing interval_ms"
                )
            return run_blink_pattern(
                self._led,
                pattern.interval_ms,
                pattern.repeat,
                self.config.id,
                self._cancel_event,
            )

        if pattern.pattern_type == "pulse":
            if pattern.duration_ms is None:
                raise InvalidPatternError(
                    f"Pulse pattern for LED '{self.config.name}' missing duration_ms"
                )
            return run_pulse_pattern(
                self._led,
                pattern.duration_ms,
                pattern.repeat,
                self.config.id,
                self._cancel_event,
            )

        if pattern.pattern_type == "glow":
            if not self._is_pwm:
                raise InvalidPatternError(
                    f"Glow pattern for LED '{self.config.name}' requires PWMLED but "
                    f"LED was initialized without PWM. Re-initialize the controller."
                )
            if (
                pattern.cycle_ms is None
                or pattern.min_brightness is None
                or pattern.max_brightness is None
            ):
                raise InvalidPatternError(
                    f"Glow pattern for LED '{self.config.name}' is missing its "
                    f"cycle or brightness bounds"
                )
            return run_glow_pattern(
                self._led,
                pattern.cycle_ms,
                pattern.min_brightness,
                pattern.max_brightness,
                pattern.repeat,
                self.config.id,
                self._cancel_event,
            )

        raise InvalidPatternError(
            f"Unknown pattern type '{pattern.pattern_type}' "
            f"for LED '{self.config.name}'"
        )

    def _launch(
        self,
        coro: Coroutine[Any, Any, None],
        logical_state: str,
        pattern_type: str,
    ) -> None:
        """Run a pattern coroutine as the LED's current task."""
        task = asyncio.create_task(coro)
        self._current_task = task
        task.add_done_callback(
            lambda finished: self._on_task_done(finished, logical_state, pattern_type)
        )

    def _on_task_done(
        self, task: asyncio.Task[None], logical_state: str, pattern_type: str
    ) -> None:
        """Release the LED's state once its pattern has finished."""
        if task.cancelled():
            return

        # Calling exception() marks it as retrieved, so asyncio will not
        # complain either. Without this branch a pattern that raised inside its
        # task left a dark LED and no log line at all.
        exc = task.exception()
        if exc is not None:
            self._current_logical_state = None
            self._current_task = None
            logger.error(
                "pattern_task_failed",
                led_id=self.config.id,
                led_name=self.config.name,
                logical_state=logical_state,
                pattern_type=pattern_type,
                error=str(exc),
                exc_info=exc,
            )
            return

        if pattern_type not in _PERSISTENT_PATTERN_TYPES:
            self._current_logical_state = None
            self._current_task = None
        logger.debug(
            "pattern_completed",
            led_id=self.config.id,
            logical_state=logical_state,
            persistent=pattern_type in _PERSISTENT_PATTERN_TYPES,
        )

    async def _cancel_current_pattern(self) -> None:
        """Cancel the currently running pattern if any.

        Callers hold ``self._lock``; this method does not take it.
        """
        if self._current_task and not self._current_task.done():
            self._cancel_event.set()
            try:
                await asyncio.wait_for(self._current_task, timeout=1.0)
            except TimeoutError:
                self._current_task.cancel()
                try:
                    await self._current_task
                except asyncio.CancelledError:
                    pass
            logger.debug("pattern_cancelled", led_id=self.config.id)
        self._current_logical_state = None
        self._current_task = None

    async def cleanup(self) -> None:
        """Release the pin and leave it pulled down (shutdown path)."""
        held_a_pin = self._led is not None
        await self.close()

        # Only at shutdown: leaving the pin floating makes an LED glimmer after
        # `docker compose down`. On a re-initialisation this would be pointless,
        # because the pin is claimed again immediately.
        if held_a_pin:
            try:
                from gpiozero import Device

                pin = Device.pin_factory.pin(self.config.gpio)
                pin.function = "input"
                pin.pull = "down"
                logger.debug(
                    "led_pin_pulldown_applied",
                    led_id=self.config.id,
                    gpio=self.config.gpio,
                )
            except Exception as exc:
                logger.warning(
                    "led_pin_pulldown_failed",
                    led_id=self.config.id,
                    gpio=self.config.gpio,
                    error=str(exc),
                    exc_info=True,
                )
        logger.debug("led_cleanup", led_id=self.config.id)

    async def run_test_blink(self, duration_sec: float = 5.0) -> bool:
        """Start a fixed blink for testing, independent of bindings (issue #27).

        Returns as soon as the blink is running rather than awaiting it. The
        backend proxies this call with a five second HTTP timeout, so a test
        blink that lasts five seconds must not be awaited here.

        Note: the test blink uses the plain on/off interface and works with
        both LED and PWMLED (PWMLED.on() sets value to 1.0).

        Args:
            duration_sec: Total blink duration in seconds.

        Returns:
            True if GPIO is available and the test was started.
        """
        if not self._gpio_available:
            logger.debug("test_blink_skipped_no_hardware", led_id=self.config.id)
            return False

        # repeat counts whole on/off blinks, so one blink costs two intervals.
        repeat = max(1, round(duration_sec * 1000 / (_TEST_BLINK_INTERVAL_MS * 2)))

        async with self._lock:
            await self._cancel_current_pattern()
            self._cancel_event.clear()
            self._current_logical_state = _TEST_BLINK_STATE
            logger.debug(
                "test_blink_started",
                led_id=self.config.id,
                led_name=self.config.name,
                duration_sec=duration_sec,
                repeat=repeat,
            )
            self._launch(
                run_blink_pattern(
                    self._led,
                    _TEST_BLINK_INTERVAL_MS,
                    repeat,
                    self.config.id,
                    self._cancel_event,
                ),
                _TEST_BLINK_STATE,
                "blink",
            )
        return True


class LEDManager:
    """Manages all LEDs for the service."""

    def __init__(self, *, disable_gpio: bool = False) -> None:
        """Initialize the LED manager.

        Args:
            disable_gpio: Skip all hardware access (development without a Pi).
        """
        self._disable_gpio = disable_gpio
        self._controllers: dict[str, LEDController] = {}
        logger.debug("led_manager_initialized", disable_gpio=disable_gpio)

    @property
    def led_count(self) -> int:
        """Number of configured LEDs."""
        return len(self._controllers)

    @property
    def available_count(self) -> int:
        """Number of LEDs that actually hold a GPIO pin."""
        return sum(1 for c in self._controllers.values() if c.is_available)

    async def initialize_leds(self, led_configs: list[LEDConfig]) -> None:
        """Initialize LED controllers from configuration.

        Each controller auto-selects LED or PWMLED based on whether any
        binding in its config requires the 'glow' pattern.

        Args:
            led_configs: List of LED configurations.
        """
        for controller in self._controllers.values():
            await controller.close()
        self._controllers.clear()

        if not self._disable_gpio:
            _ensure_pin_factory()

        for config in led_configs:
            self._controllers[config.id] = LEDController(
                config, disable_gpio=self._disable_gpio
            )

        logger.debug(
            "leds_initialized",
            count=self.led_count,
            available=self.available_count,
        )

        # A wrong GPIO group id after an update leaves every pin unclaimable.
        # Without this the service looks perfectly healthy while none of the
        # LEDs can ever light up again.
        enabled = [c for c in self._controllers.values() if c.config.enabled]
        if enabled and not self.available_count and not self._disable_gpio:
            logger.warning(
                "no_leds_available",
                configured=len(enabled),
                detail=(
                    "Every configured LED failed to claim its GPIO pin. Check "
                    "GPIO_GID in .env and the /dev/gpiochip0 device mapping."
                ),
            )

    async def apply_state(self, logical_state: str) -> None:
        """Apply a logical state to all LEDs that have bindings for it.

        Args:
            logical_state: The logical state to apply (e.g. 'audio_playing').
        """
        logger.debug("applying_state", logical_state=logical_state)

        tasks = [
            controller.apply_pattern(logical_state)
            for controller in self._controllers.values()
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_led(self, led_id: str) -> bool:
        """Start a fixed test blink on one LED.

        Args:
            led_id: The LED ID to test.
        """
        controller = self._controllers.get(led_id)
        if not controller:
            logger.warning("test_led_not_found", led_id=led_id)
            return False
        return await controller.run_test_blink()

    async def cleanup(self) -> None:
        """Clean up all LED controllers."""
        tasks = [controller.cleanup() for controller in self._controllers.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._controllers.clear()
        logger.debug("led_manager_cleanup")
