from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import structlog
from gpiozero import Button, Device, RotaryEncoder

from ..config_schema import ButtonConfig, ButtonServiceConfig
from ..exceptions import GPIOInitError
from .events import RawButtonEvent
from .state_machine import EncoderRotationEmitter, EncoderSwitchEmitter, PressClassifier

logger = structlog.get_logger(__name__)

@dataclass(slots=True)
class GPIOInputManager:
    """Manage gpiozero input devices and emit normalized RawButtonEvents.

    Notes:
    - gpiozero callbacks are executed in background threads; therefore we must
      forward events into asyncio safely via `loop.call_soon_threadsafe(...)`.
    - This manager only deals with raw events; mapping to logical actions and
      MQTT publishing happens elsewhere.
    """

    config: ButtonServiceConfig
    event_queue: asyncio.Queue[RawButtonEvent]
    loop: asyncio.AbstractEventLoop
    push_hold_time_s: float = 1.0
    push_bounce_time_s: float | None = 0.05
    _devices: list[object] = field(default_factory=list, init=False)

    def start(self) -> None:
        """Initialize gpiozero devices and register callbacks."""
        # Use lgpio pin factory explicitly (works in Docker with /dev/gpiochip0; no sysfs)
        # Lazy import so the service can start even when lgpio is not installed (e.g. DISABLE_GPIO).
        if Device.pin_factory is None or type(Device.pin_factory).__name__ != "LGPIOFactory":
            try:
                from gpiozero.pins.lgpio import LGPIOFactory
            except ImportError as exc:
                logger.error(
                    "gpio_pin_factory_unavailable",
                    factory="lgpio",
                    hint="Rebuild the button image so liblgpio/lgpio is installed (see Dockerfile).",
                )
                raise GPIOInitError(
                    "lgpio module not found; rebuild image with liblgpio built from source"
                ) from exc
            try:
                if Device.pin_factory is not None:
                    Device.pin_factory.close()
                Device.pin_factory = LGPIOFactory()
                logger.info("gpio_pin_factory_set", factory="lgpio")
            except Exception as exc:
                logger.error("gpio_pin_factory_init_failed", factory="lgpio", error=str(exc))
                raise GPIOInitError("Failed to initialize lgpio pin factory") from exc

        logger.info("gpio_inputs_starting", buttons=len(self.config.buttons))

        for btn in self.config.buttons:
            try:
                self._init_device(btn)
            except Exception as exc:
                logger.error(
                    "gpio_input_init_failed",
                    button_id=btn.id,
                    button_type=btn.type,
                    error=str(exc),
                    exc_info=True,
                )
                raise GPIOInitError(f"Failed to initialize input device {btn.id}") from exc

        logger.info("gpio_inputs_started", devices=len(self._devices))

    def close(self) -> None:
        """Close all gpiozero devices."""
        logger.info("gpio_inputs_stopping", devices=len(self._devices))
        for dev in self._devices:
            close = getattr(dev, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    logger.warning("gpio_device_close_failed", error=str(exc), exc_info=True)
        self._devices.clear()
        logger.info("gpio_inputs_stopped")

    def _emit_threadsafe(self, event: RawButtonEvent) -> None:
        self.loop.call_soon_threadsafe(self.event_queue.put_nowait, event)

    def _init_device(self, btn: ButtonConfig) -> None:
        if btn.type == "push":
            assert btn.gpio is not None  # validated by schema
            device = Button(
                btn.gpio,
                pull_up=True,
                bounce_time=self.push_bounce_time_s,
                hold_time=self.push_hold_time_s,
                hold_repeat=False,
            )
            classifier = PressClassifier(source_id=btn.id, emit=self._emit_threadsafe)
            device.when_pressed = classifier.on_pressed
            device.when_held = classifier.on_held
            device.when_released = classifier.on_released
            self._devices.append(device)
            logger.info("gpio_push_button_initialized", button_id=btn.id, gpio=btn.gpio)
            return

        if btn.type == "rotary":
            assert btn.clk is not None and btn.dt is not None and btn.sw is not None

            encoder = RotaryEncoder(
                btn.clk,
                btn.dt,
                bounce_time=self.push_bounce_time_s,
                max_steps=0,
                wrap=False,
            )
            rotation = EncoderRotationEmitter(source_id=btn.id, emit=self._emit_threadsafe)
            encoder.when_rotated_clockwise = rotation.on_clockwise
            encoder.when_rotated_counter_clockwise = rotation.on_counter_clockwise

            switch = Button(
                btn.sw,
                pull_up=True,
                bounce_time=self.push_bounce_time_s,
            )
            switch_emitter = EncoderSwitchEmitter(source_id=btn.id, emit=self._emit_threadsafe)
            switch.when_pressed = switch_emitter.on_pressed

            self._devices.extend([encoder, switch])
            logger.info(
                "gpio_rotary_encoder_initialized",
                encoder_id=btn.id,
                clk=btn.clk,
                dt=btn.dt,
                sw=btn.sw,
            )
            return

        raise ValueError(f"Unsupported button type: {btn.type}")

