"""LED controller for managing physical GPIO-based LEDs.

This module handles:
- Initialization of GPIO pins via gpiozero (NativePinFactory)
- Pattern execution and cancellation
- LED state management with graceful fallback for dev environments
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
    run_off_pattern,
    run_pulse_pattern,
    run_solid_pattern,
)

logger = structlog.get_logger(__name__)

# Pattern types that represent persistent states (LED stays as-is after task finishes).
# These must NOT clear _current_logical_state so subsequent identical events are
# correctly suppressed by the idempotency check in apply_pattern().
_PERSISTENT_PATTERN_TYPES = frozenset({"solid", "off"})


class LEDController:
    """Controls a single physical LED and its pattern execution."""

    def __init__(self, config: LEDConfig) -> None:
        """Initialize LED controller with direct NativePinFactory.
        
        Args:
            config: LED configuration including GPIO pin and bindings.
        """
        self.config = config
        self._current_task: asyncio.Task[None] | None = None
        self._cancel_event = asyncio.Event()
        self._current_logical_state: str | None = None  # skip re-apply when state unchanged
        self._gpio_available = False
        self._led = None
        
        # Check if GPIO should be disabled (dev mode)
        disable_gpio = os.getenv("DISABLE_GPIO", "false").lower() == "true"
        
        if disable_gpio:
            logger.debug(
                "gpio_disabled_dev_mode",
                led_id=config.id,
                led_name=config.name,
                reason="DISABLE_GPIO environment variable",
            )
            return
        
        # Try to initialize GPIO with NativePinFactory directly
        try:
            from gpiozero.pins.native import NativeFactory
            from gpiozero import Device, LED
            
            # Set pin factory explicitly to avoid fallback warnings
            Device.pin_factory = NativeFactory()
            
            self._led = LED(config.gpio)
            self._gpio_available = True
            logger.debug(
                "led_initialized",
                led_id=config.id,
                led_name=config.name,
                gpio=config.gpio,
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
            # Service continues without hardware

    async def apply_pattern(self, logical_state: str) -> None:
        """Apply the pattern for a given logical state.
        
        Args:
            logical_state: The logical state to apply (e.g. 'audio_playing').
        """
        if not self._gpio_available:
            logger.debug(
                "pattern_skipped_no_hardware",
                led_id=self.config.id,
                logical_state=logical_state,
            )
            return
        
        # Check if we have a binding for this state
        pattern = self.config.bindings.get(logical_state)
        if pattern is None:
            logger.debug(
                "no_pattern_binding",
                led_id=self.config.id,
                logical_state=logical_state,
            )
            return

        # Idempotent: skip only if the same state is actively running (avoids
        # cancel/restart spam for periodic status messages). One-shot patterns
        # (solid, blink with repeat) finish their task quickly; once the task
        # is done _current_logical_state is cleared so the state can be
        # re-triggered (e.g. rfid_scanned on every new scan).
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
        
        # Cancel any running pattern
        await self._cancel_current_pattern()
        
        # Start new pattern
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
                    pattern.duration_ms,
                    self.config.id,
                )
            )
        elif pattern.pattern_type == "off":
            # Just ensure the LED is off without any visible pulse
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
        else:
            raise InvalidPatternError(
                f"Unknown pattern type '{pattern.pattern_type}' for LED '{self.config.name}'"
            )

        # When a one-shot (non-persistent) pattern finishes on its own, clear the
        # state so the same logical state can be re-triggered later
        # (e.g. rfid_scanned on every new scan).
        # Persistent patterns (solid, off) intentionally keep _current_logical_state
        # set so that repeated identical events (e.g. system_online heartbeats) are
        # correctly suppressed by the idempotency check in apply_pattern().
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
        # Always reset state – even if the task already finished on its own
        self._current_logical_state = None
        self._current_task = None

    async def cleanup(self) -> None:
        """Clean up resources (cancel pattern, turn off LED)."""
        await self._cancel_current_pattern()
        if self._led:
            # Try to leave the GPIO pin in a defined low state with pull-down
            try:
                # First ensure the LED is off while we still have the LED wrapper
                self._led.off()
            finally:
                # Close the gpiozero LED object to release resources
                try:
                    self._led.close()
                except Exception:
                    # If close fails we still try to enforce a safe pin state
                    logger.warning("led_close_failed", led_id=self.config.id, exc_info=True)
            
            # After closing the LED, explicitly configure the pin as input with pull-down.
            # This prevents the LED from faint glowing caused by leakage currents
            # once the service (or container) has stopped.
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
                # In worst case we fall back to whatever state gpiozero left the pin in
                logger.warning(
                    "led_pin_pulldown_failed",
                    led_id=self.config.id,
                    gpio=self.config.gpio,
                    error=str(exc),
                    exc_info=True,
                )
        logger.debug("led_cleanup", led_id=self.config.id)

    async def run_test_blink(self, duration_sec: float = 5.0) -> bool:
        """Run a fixed blink pattern for testing (e.g. 5 seconds), independent of bindings.

        Does not set _current_logical_state so normal state handling is unaffected.
        Returns True if the LED is available and test was started, False otherwise.

        Args:
            duration_sec: Total blink duration in seconds.
        """
        if not self._gpio_available:
            logger.debug(
                "test_blink_skipped_no_hardware",
                led_id=self.config.id,
            )
            return False

        await self._cancel_current_pattern()
        self._cancel_event.clear()

        # 500 ms on/off = 1 cycle per second; repeat = duration in seconds
        interval_ms = 500
        repeat = max(1, int(duration_sec))
        logger.debug(
            "test_blink_started",
            led_id=self.config.id,
            led_name=self.config.name,
            duration_sec=duration_sec,
        )
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

        def _on_done(_t: asyncio.Task) -> None:
            self._current_task = None

        task.add_done_callback(_on_done)
        try:
            await task
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

        Properly awaits cleanup of existing controllers before creating new ones
        to prevent transient GPIO pin conflicts on the same pins.
        
        Args:
            led_configs: List of LED configurations.
        """
        for controller in self._controllers.values():
            await controller.cleanup()
        self._controllers.clear()
        
        # Initialize new controllers
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

        Does not use bindings; the LED blinks for 5 seconds regardless of
        configured patterns. Returns True if the LED was found and test ran.

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
