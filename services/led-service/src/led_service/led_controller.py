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

from .config_schema import LEDConfig, LEDPattern
from .exceptions import GPIOControlError, GPIOInitError, InvalidPatternError
from .led_patterns import (
    run_blink_pattern,
    run_off_pattern,
    run_pulse_pattern,
    run_solid_pattern,
)

logger = structlog.get_logger(__name__)

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
        self._gpio_available = False
        self._led = None
        
        # Check if GPIO should be disabled (dev mode)
        disable_gpio = os.getenv("DISABLE_GPIO", "false").lower() == "true"
        
        if disable_gpio:
            logger.info(
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
            logger.info(
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
        
        logger.info(
            "pattern_started",
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
            # This helps prevent the LED from leichtes Glimmen durch Leckströme,
            # once the service (or container) has stopped.
            try:
                from gpiozero import Device
                
                pin = Device.pin_factory.pin(self.config.gpio)
                pin.function = "input"
                pin.pull = "down"
                logger.info(
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
        logger.info("led_cleanup", led_id=self.config.id)

class LEDManager:
    """Manages all LEDs for the service."""

    def __init__(self) -> None:
        """Initialize the LED manager."""
        self._controllers: Dict[str, LEDController] = {}
        logger.info("led_manager_initialized")

    def initialize_leds(self, led_configs: list[LEDConfig]) -> None:
        """Initialize LED controllers from configuration.
        
        Args:
            led_configs: List of LED configurations.
        """
        # Clean up existing controllers
        for controller in self._controllers.values():
            asyncio.create_task(controller.cleanup())
        self._controllers.clear()
        
        # Initialize new controllers
        for config in led_configs:
            controller = LEDController(config)
            self._controllers[config.id] = controller
        
        logger.info("leds_initialized", count=len(self._controllers))

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

    async def cleanup(self) -> None:
        """Clean up all LED controllers."""
        tasks = [controller.cleanup() for controller in self._controllers.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._controllers.clear()
        logger.info("led_manager_cleanup")
