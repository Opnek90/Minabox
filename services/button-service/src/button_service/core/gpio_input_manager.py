from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import structlog
from gpiozero import Button, Device, RotaryEncoder

from ..config_schema import ButtonConfig, ButtonServiceConfig
from ..exceptions import GPIOInitError
from .events import RawButtonEvent
from .state_machine import (
    EncoderRotationEmitter,
    EncoderSwitchEmitter,
    PressClassifier,
)

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class GPIOInputManager:
    """Manage gpiozero input devices and emit normalized RawButtonEvents.

    Notes:
    - gpiozero callbacks are executed in background threads; therefore we must
      forward events into asyncio safely via `loop.call_soon_threadsafe(...)`.
    - This manager only deals with raw events; mapping to logical actions and
      MQTT publishing happens elsewhere.
    - A button whose pin cannot be claimed is skipped, not fatal. It used to
      abort the whole start, which left every other button dead *and* leaked
      the pins already claimed, because the caller dropped the manager without
      closing it. `available_count` reports what really came up.
    """

    config: ButtonServiceConfig
    event_queue: asyncio.Queue[RawButtonEvent]
    loop: asyncio.AbstractEventLoop
    push_hold_time_s: float = 1.0
    push_bounce_time_s: float | None = 0.05
    _devices: list[object] = field(default_factory=list, init=False)
    _classifiers: list[PressClassifier] = field(default_factory=list, init=False)
    _available: set[str] = field(default_factory=set, init=False)

    @property
    def configured_count(self) -> int:
        """Number of buttons in the configuration this manager was built from."""
        return len(self.config.buttons)

    @property
    def available_count(self) -> int:
        """Number of buttons that actually hold their GPIO pins."""
        return len(self._available)

    def start(self) -> None:
        """Initialize gpiozero devices and register callbacks.

        Raises:
            GPIOInitError: if the lgpio pin factory itself is unusable. A single
                button that cannot claim its pin is logged and skipped instead.
        """
        self._ensure_pin_factory()

        logger.debug("gpio_inputs_starting", buttons=len(self.config.buttons))

        for btn in self.config.buttons:
            try:
                self._init_device(btn)
            except Exception as exc:
                # Do not take the other buttons down with this one. The most
                # common cause is a pin that some other service already owns
                # (see the LED/button pin conflict in the service README).
                logger.error(
                    "gpio_input_init_failed",
                    button_id=btn.id,
                    button_type=btn.type,
                    error=str(exc),
                    hint=(
                        "Pin is unavailable; check for an overlap with "
                        "config/leds.json. This button stays inactive."
                    ),
                    exc_info=True,
                )
            else:
                self._available.add(btn.id)

        if self.config.buttons and not self._available:
            logger.warning(
                "no_buttons_available",
                configured=len(self.config.buttons),
                detail=(
                    "Every configured button failed to claim its GPIO pin. "
                    "Check GPIO_GID in .env and the /dev/gpiochip0 mapping."
                ),
            )

        logger.debug(
            "gpio_inputs_started",
            devices=len(self._devices),
            configured=self.configured_count,
            available=self.available_count,
        )

    def _ensure_pin_factory(self) -> None:
        """Select the lgpio pin factory, which is the only one that works here.

        Uses lgpio explicitly because it talks to /dev/gpiochip0 and therefore
        works inside the container; the sysfs-based factories do not. The
        import is lazy so the service can still start when lgpio is missing.
        """
        if (
            Device.pin_factory is not None
            and type(Device.pin_factory).__name__ == "LGPIOFactory"
        ):
            return

        try:
            from gpiozero.pins.lgpio import LGPIOFactory
        except ImportError as exc:
            logger.error(
                "gpio_pin_factory_unavailable",
                factory="lgpio",
                hint=(
                    "Rebuild the button image so liblgpio/lgpio is installed "
                    "(see Dockerfile)."
                ),
            )
            raise GPIOInitError(
                "lgpio module not found; rebuild image with liblgpio built from source"
            ) from exc

        try:
            if Device.pin_factory is not None:
                Device.pin_factory.close()
            Device.pin_factory = LGPIOFactory()
            logger.debug("gpio_pin_factory_set", factory="lgpio")
        except Exception as exc:
            logger.error(
                "gpio_pin_factory_init_failed", factory="lgpio", error=str(exc)
            )
            raise GPIOInitError("Failed to initialize lgpio pin factory") from exc

    def close(self) -> None:
        """Close all gpiozero devices and cancel pending classifier timers."""
        logger.debug("gpio_inputs_stopping", devices=len(self._devices))

        # Before the devices: a pending double-press timer would otherwise fire
        # into an event loop that may already be gone, or emit an event for a
        # button id the reloaded configuration no longer knows.
        for classifier in self._classifiers:
            classifier.cancel_pending()
        self._classifiers.clear()

        for dev in self._devices:
            close = getattr(dev, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    logger.warning(
                        "gpio_device_close_failed", error=str(exc), exc_info=True
                    )
        self._devices.clear()
        self._available.clear()
        logger.debug("gpio_inputs_stopped")

    def _emit_threadsafe(self, event: RawButtonEvent) -> None:
        try:
            self.loop.call_soon_threadsafe(self.event_queue.put_nowait, event)
        except RuntimeError:
            # The loop is closing. Nothing left to deliver the event to, and a
            # gpiozero callback thread must not raise.
            logger.debug("event_dropped_loop_closed", source_id=event.source_id)

    def _init_device(self, btn: ButtonConfig) -> None:
        """Create the devices for one button, or leave nothing behind.

        Devices are collected locally and only handed over once the whole
        button succeeded. A rotary encoder whose switch fails to claim its pin
        must not leave the encoder itself claimed.
        """
        created: list[object] = []
        classifiers: list[PressClassifier] = []
        try:
            if btn.type == "push":
                assert btn.gpio is not None  # validated by schema
                device = Button(
                    btn.gpio,
                    pull_up=True,
                    bounce_time=self.push_bounce_time_s,
                    hold_time=self.push_hold_time_s,
                    hold_repeat=False,
                )
                created.append(device)
                classifier = PressClassifier(
                    source_id=btn.id, emit=self._emit_threadsafe
                )
                classifiers.append(classifier)
                device.when_pressed = classifier.on_pressed
                device.when_held = classifier.on_held
                device.when_released = classifier.on_released
                logger.debug(
                    "gpio_push_button_initialized", button_id=btn.id, gpio=btn.gpio
                )

            elif btn.type == "rotary":
                assert btn.clk is not None and btn.dt is not None and btn.sw is not None

                encoder = RotaryEncoder(
                    btn.clk,
                    btn.dt,
                    bounce_time=self.push_bounce_time_s,
                    max_steps=0,
                    wrap=False,
                )
                created.append(encoder)
                rotation = EncoderRotationEmitter(
                    source_id=btn.id, emit=self._emit_threadsafe
                )
                encoder.when_rotated_clockwise = rotation.on_clockwise
                encoder.when_rotated_counter_clockwise = rotation.on_counter_clockwise

                switch = Button(
                    btn.sw,
                    pull_up=True,
                    bounce_time=self.push_bounce_time_s,
                )
                created.append(switch)
                switch_emitter = EncoderSwitchEmitter(
                    source_id=btn.id, emit=self._emit_threadsafe
                )
                switch.when_pressed = switch_emitter.on_pressed

                logger.debug(
                    "gpio_rotary_encoder_initialized",
                    encoder_id=btn.id,
                    clk=btn.clk,
                    dt=btn.dt,
                    sw=btn.sw,
                )

            else:
                raise ValueError(f"Unsupported button type: {btn.type}")

        except Exception:
            for dev in created:
                try:
                    dev.close()  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001 - cleanup must not mask the cause
                    pass
            raise

        self._devices.extend(created)
        self._classifiers.extend(classifiers)
