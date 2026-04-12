"""LED controller for managing physical GPIO-based LEDs.

This module handles:
- Initialization of GPIO pins via gpiozero (LGPIOFactory for PWMLED support)
- Pattern execution and cancellation
- LED state management with graceful fallback for dev environments
- PWM support for the 'glow' pattern via PWMLED
"""

from __future__ import annotations

import asyncio
import os
from typing import Dict

import structlog

from ..config_schema import LEDConfig, LEDPattern
from ..exceptions import GPIOControlError, GPIOInitError, InvalidPatternError
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


def _led_needs_pwm(config: LEDConfig) -> bool:
    """Return True if any binding in this LED config requires PWM (PWMLED)."""
    return any(p.pattern_type == "glow" for p in config.bindings.values())


class LEDController:
    """Controls a single physical LED and its pattern execution."""

    def __init__(self, config: LEDConfig) -> None:
        """Initialize LED controller.

        GPIO pin factory is expected to be set once by LEDManager before
        instantiating controllers (issue #36).

        If any binding uses the 'glow' pattern, PWMLED is instantiated
        instead of LED. PWMLED is backward-compatible: value=1.0 equals on(),
        value=0.0 equals off().

        Args:
            config: LED configuration including GPIO pin and bindings.
        """
        self.config = config
        self._current_task: asyncio.Task[None] | None = None
        self._cancel_event = asyncio.Event()
        self._current_logical_state: str | None = None
        self._gpio_available = False
        self._led = None
        self._is_pwm = False

        disable_gpio = os.getenv("DISABLE_GPIO", "false").lower() == "true"

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

    def close_sync(self) -> None:
        """Synchronous close for re-initialization without await (issue #37).

        Cancels any running task and releases the GPIO LED object.
        Called by LEDManager.initialize_leds() before creating new controllers.
        Works with both LED and PWMLED instances.
        """
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        if self._led is not None:
            try:
                if self._is_pwm:
                    self._led.value = 0.0
                else:
                    self._led.off()
                self._led.close()
            except Exception:
                pass
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

        if (
            self._current_logical_state == logical_state
            and self._current_task is not None
            and not self._current_task.done()
        ):
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

    async def _run_blink_task(self, interval_ms: int, repeat: int) -> None:
        """Create and await a blink task, managing _current_task lifecycle (issue #27).

        Shared by _start_pattern(blink) and run_test_blink() to avoid
        duplicated task-creation boilerplate.
        """
        self._cancel_event.clear()
        task = asyncio.create_task(
            run_blink_pattern(
                self._led,
                interval_ms,
                repeat,
                self.config.id,
                self._cancel_event,
            )
        )
        self._current_task = task
        task.add_done_callback(lambda _: setattr(self, "_current_task", None))
        await task

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

        if pattern.pattern_type == "solid":
            self._current_task = asyncio.create_task(
                run_solid_pattern(
                    self._led,
                    self.config.id,
                )
            )
        elif pattern.pattern_type == "off":
            self._current_task = asyncio.create_task(
                run_off_pattern(
                    self._led,
                    self.config.id,
                )
            )
        elif pattern.pattern_type == "blink":
            if pattern.interval_ms is None:
                raise InvalidPatternError(
                    f"Blink pattern for LED '{self.config.name}' missing interval_ms"
                )
            self._current_task = asyncio.create_task(
                run_blink_pattern(
                    self._led,
                    pattern.interval_ms,
                    pattern.repeat,
                    self.config.id,
                    self._cancel_event,
                )
            )
        elif pattern.pattern_type == "pulse":
            if pattern.duration_ms is None:
                raise InvalidPatternError(
                    f"Pulse pattern for LED '{self.config.name}' missing duration_ms"
                )
            self._current_task = asyncio.create_task(
                run_pulse_pattern(
                    self._led,
                    pattern.duration_ms,
                    pattern.repeat,
                    self.config.id,
                    self._cancel_event,
                )
            )
        elif pattern.pattern_type == "glow":
            if not self._is_pwm:
                raise InvalidPatternError(
                    f"Glow pattern for LED '{self.config.name}' requires PWMLED but "
                    f"LED was initialized without PWM. Re-initialize the controller."
                )
            self._current_task = asyncio.create_task(
                run_glow_pattern(
                    self._led,
                    pattern.cycle_ms if pattern.cycle_ms is not None else 2000,
                    pattern.min_brightness if pattern.min_brightness is not None else 0.0,
                    pattern.max_brightness if pattern.max_brightness is not None else 1.0,
                    pattern.repeat,
                    self.config.id,
                    self._cancel_event,
                )
            )
        else:
            raise InvalidPatternError(
                f"Unknown pattern type '{pattern.pattern_type}' for LED '{self.config.name}'"
            )

        _pattern_type = pattern.pattern_type

        def _on_task_done(task: asyncio.Task) -> None:
            if not task.cancelled() and task.exception() is None:
                if _pattern_type not in _PERSISTENT_PATTERN_TYPES:
                    self._current_logical_state = None
                    self._current_task = None
                logger.debug(
                    "pattern_completed",
                    led_id=self.config.id,
                    logical_state=logical_state,
                    persistent=_pattern_type in _PERSISTENT_PATTERN_TYPES,
                )

        self._current_task.add_done_callback(_on_task_done)

    async def _cancel_current_pattern(self) -> None:
        """Cancel the currently running pattern if any."""
        if self._current_task and not self._current_task.done():
            self._cancel_event.set()
            try:
                await asyncio.wait_for(self._current_task, timeout=1.0)
            except asyncio.TimeoutError:
                self._current_task.cancel()
                try:
                    await self._current_task
                except asyncio.CancelledError:
                    pass
            logger.debug("pattern_cancelled", led_id=self.config.id)
        self._current_logical_state = None
        self._current_task = None

    async def cleanup(self) -> None:
        """Clean up resources (cancel pattern, turn off LED)."""
        await self._cancel_current_pattern()
        if self._led:
            try:
                if self._is_pwm:
                    self._led.value = 0.0
                else:
                    self._led.off()
            finally:
                try:
                    self._led.close()
                except Exception:
                    logger.warning("led_close_failed", led_id=self.config.id, exc_info=True)

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
        """Run a fixed blink pattern for testing, independent of bindings (issue #27).

        Delegates to _run_blink_task() to avoid duplicating task-creation logic.
        Returns True if GPIO is available and test was started, False otherwise.

        Note: test_blink uses the plain on/off interface and is compatible with
        both LED and PWMLED (PWMLED.on() sets value to 1.0).

        Args:
            duration_sec: Total blink duration in seconds.
        """
        if not self._gpio_available:
            logger.debug("test_blink_skipped_no_hardware", led_id=self.config.id)
            return False

        await self._cancel_current_pattern()
        interval_ms = 500
        repeat = max(1, int(duration_sec))
        logger.debug(
            "test_blink_started",
            led_id=self.config.id,
            led_name=self.config.name,
            duration_sec=duration_sec,
        )
        try:
            await self._run_blink_task(interval_ms, repeat)
        finally:
            self._current_task = None
        logger.debug("test_blink_finished", led_id=self.config.id)
        return True


class LEDManager:
    """Manages all LEDs for the service."""

    def __init__(self) -> None:
        """Initialize the LED manager."""
        self._controllers: Dict[str, LEDController] = {}
        logger.debug("led_manager_initialized")

    async def initialize_leds(self, led_configs: list[LEDConfig]) -> None:
        """Initialize LED controllers from configuration.

        Sets the gpiozero pin factory to LGPIOFactory exactly once before
        creating controllers. LGPIOFactory (via lgpio) supports Software-PWM
        (PWMLED) via /dev/gpiochip0 inside Docker without a pigpiod daemon.
        NativeFactory does NOT support PWM and is no longer used (issue #36).

        Each controller auto-selects LED or PWMLED based on whether any
        binding in its config requires the 'glow' pattern.

        Args:
            led_configs: List of LED configurations.
        """
        for controller in self._controllers.values():
            controller.close_sync()
        self._controllers.clear()

        disable_gpio = os.getenv("DISABLE_GPIO", "false").lower() == "true"
        if not disable_gpio:
            try:
                from gpiozero.pins.lgpio import LGPIOFactory
                from gpiozero import Device
                Device.pin_factory = LGPIOFactory()
                logger.debug("gpio_pin_factory_set", factory="LGPIOFactory")
            except Exception as exc:
                logger.warning("gpio_pin_factory_set_failed", error=str(exc))

        for config in led_configs:
            controller = LEDController(config)
            self._controllers[config.id] = controller

        logger.debug("leds_initialized", count=len(self._controllers))

    async def apply_state(self, logical_state: str) -> None:
        """Apply a logical state to all LEDs that have bindings for it.

        Args:
            logical_state: The logical state to apply (e.g. 'audio_playing').
        """
        logger.debug("applying_state", logical_state=logical_state)

        tasks = []
        for controller in self._controllers.values():
            tasks.append(controller.apply_pattern(logical_state))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_led(self, led_id: str) -> bool:
        """Run a fixed 5-second blink on the LED for testing.

        Args:
            led_id: The LED ID to test.
        """
        controller = self._controllers.get(led_id)
        if not controller:
            logger.warning("test_led_not_found", led_id=led_id)
            return False
        return await controller.run_test_blink(duration_sec=5.0)

    async def cleanup(self) -> None:
        """Clean up all LED controllers."""
        tasks = [controller.cleanup() for controller in self._controllers.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._controllers.clear()
        logger.debug("led_manager_cleanup")
